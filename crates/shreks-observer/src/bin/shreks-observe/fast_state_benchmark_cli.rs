use std::{
    ffi::OsString,
    fs,
    hint::black_box,
    io,
    time::Instant,
};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FastMarketState, FastReserveContext,
    LifecycleEventKind, ProviderId, TokenLifecycleEvent, VenueId,
};

const BENCHMARK_VERSION: u64 = 2;
const BENCHMARK_STATE_SHAPE: &str = "reserve+lifecycle";
const WSOL_MINT: &str = "So11111111111111111111111111111111111111112";
const OBSERVED_BASE_UNIX_MS: i64 = 1_800_000_000_000;

pub fn run_fast_state_benchmark_subcommand_if_requested() -> io::Result<bool> {
    let mut args = std::env::args_os();
    let program = args
        .next()
        .unwrap_or_else(|| OsString::from("shreks-observe"));

    let Some(command) = args.next() else {
        return Ok(false);
    };
    if command != "fast-state-benchmark" {
        return Ok(false);
    }

    let active_markets = parse_positive_usize(
        required_argument(&mut args, &program, "active_markets")?,
        "active_markets",
    )?;
    let burst_events = parse_positive_usize(
        required_argument(&mut args, &program, "burst_events")?,
        "burst_events",
    )?;
    let state_update_samples = parse_positive_usize(
        required_argument(&mut args, &program, "state_update_samples")?,
        "state_update_samples",
    )?;
    if args.next().is_some() {
        return Err(io::Error::other(usage(&program)));
    }

    let report = run_benchmark(active_markets, burst_events, state_update_samples)?;
    print_report(&report);
    Ok(true)
}

#[derive(Debug)]
struct FastStateBenchmarkReport {
    active_markets: usize,
    burst_events: usize,
    state_update_samples: usize,
    events_per_second: f64,
    apply_latency: LatencySummary,
    state_update_latency: LatencySummary,
    rss_before_bytes: Option<u64>,
    rss_after_state_init_bytes: Option<u64>,
    rss_state_init_delta_bytes: Option<u64>,
    rss_bytes_per_active_market: Option<u64>,
    rss_after_burst_bytes: Option<u64>,
    snapshot_checksum: u64,
}

#[derive(Debug)]
struct LatencySummary {
    p50_ns: u128,
    p95_ns: u128,
    p99_ns: u128,
    max_ns: u128,
}

fn run_benchmark(
    active_markets: usize,
    burst_events: usize,
    state_update_samples: usize,
) -> io::Result<FastStateBenchmarkReport> {
    let rss_before_bytes = rss_bytes()?;

    let markets = (0..active_markets)
        .map(benchmark_market)
        .collect::<io::Result<Vec<_>>>()?;
    let mut states = markets
        .iter()
        .cloned()
        .map(FastMarketState::with_default_windows)
        .collect::<Vec<_>>();

    for (index, state) in states.iter_mut().enumerate() {
        let sequence = u64::try_from(index)
            .map_err(|_| io::Error::other("active market index exceeds u64"))?
            .checked_add(1)
            .ok_or_else(|| io::Error::other("seed sequence overflow"))?;
        let observed_at_unix_ms = OBSERVED_BASE_UNIX_MS
            .checked_add(i64::try_from(index).map_err(|_| {
                io::Error::other("active market index exceeds i64 milliseconds")
            })?)
            .ok_or_else(|| io::Error::other("seed observation timestamp overflow"))?;
        let lifecycle_detected_at_unix_ms = observed_at_unix_ms
            .checked_sub(1)
            .ok_or_else(|| io::Error::other("benchmark lifecycle timestamp underflow"))?;

        state
            .apply_lifecycle(benchmark_lifecycle_event(
                index,
                &markets[index],
                sequence,
                lifecycle_detected_at_unix_ms,
            ))
            .map_err(|error| io::Error::other(error.to_string()))?;
        state
            .apply(benchmark_event(
                sequence,
                markets[index].clone(),
                observed_at_unix_ms,
            )?)
            .map_err(|error| io::Error::other(error.to_string()))?;
    }

    black_box(&states);
    let rss_after_state_init_bytes = rss_bytes()?;
    let rss_state_init_delta_bytes = option_delta(rss_before_bytes, rss_after_state_init_bytes);
    let rss_bytes_per_active_market = rss_state_init_delta_bytes
        .map(|delta| delta / u64::try_from(active_markets).unwrap_or(u64::MAX));

    let mut next_sequence = u64::try_from(active_markets)
        .map_err(|_| io::Error::other("active market count exceeds u64"))?
        .checked_add(1)
        .ok_or_else(|| io::Error::other("benchmark sequence overflow"))?;
    let mut next_observed_at_unix_ms = OBSERVED_BASE_UNIX_MS
        .checked_add(
            i64::try_from(active_markets)
                .map_err(|_| io::Error::other("active market count exceeds i64"))?,
        )
        .and_then(|value| value.checked_add(1))
        .ok_or_else(|| io::Error::other("benchmark observation timestamp overflow"))?;

    let hot_market = markets[0].clone();
    let mut apply_samples = Vec::with_capacity(burst_events);
    let burst_started = Instant::now();
    for _ in 0..burst_events {
        let event = benchmark_event(next_sequence, hot_market.clone(), next_observed_at_unix_ms)?;
        let started = Instant::now();
        states[0]
            .apply(event)
            .map_err(|error| io::Error::other(error.to_string()))?;
        apply_samples.push(started.elapsed().as_nanos());
        next_sequence = next_sequence
            .checked_add(1)
            .ok_or_else(|| io::Error::other("benchmark sequence overflow"))?;
        next_observed_at_unix_ms = next_observed_at_unix_ms
            .checked_add(1)
            .ok_or_else(|| io::Error::other("benchmark observation timestamp overflow"))?;
    }
    let burst_elapsed = burst_started.elapsed();
    let events_per_second = burst_events as f64 / burst_elapsed.as_secs_f64().max(f64::MIN_POSITIVE);
    black_box(&states[0]);
    let rss_after_burst_bytes = rss_bytes()?;

    let mut state_update_latencies = Vec::with_capacity(state_update_samples);
    let mut snapshot_checksum = 0_u64;
    for _ in 0..state_update_samples {
        let observed_at_unix_ms = next_observed_at_unix_ms;
        let event = benchmark_event(next_sequence, hot_market.clone(), observed_at_unix_ms)?;
        let started = Instant::now();
        states[0]
            .apply(event)
            .map_err(|error| io::Error::other(error.to_string()))?;
        let snapshot = states[0]
            .snapshot(observed_at_unix_ms)
            .map_err(|error| io::Error::other(error.to_string()))?;
        state_update_latencies.push(started.elapsed().as_nanos());

        let one_second = snapshot
            .window(1_000)
            .ok_or_else(|| io::Error::other("benchmark snapshot missing 1s window"))?;
        let reserve_checksum = match snapshot.last_reserve_context.as_ref() {
            Some(FastReserveContext::PumpCurve {
                virtual_base_reserve_raw,
                virtual_quote_reserve_raw,
                real_base_reserve_raw,
                real_quote_reserve_raw,
                base_decimals,
                quote_decimals,
            }) => virtual_base_reserve_raw
                ^ virtual_quote_reserve_raw.rotate_left(7)
                ^ real_base_reserve_raw.rotate_left(13)
                ^ real_quote_reserve_raw.rotate_left(19)
                ^ u64::from(*base_decimals).rotate_left(29)
                ^ u64::from(*quote_decimals).rotate_left(37),
            Some(FastReserveContext::PumpSwapPool { .. }) => {
                return Err(io::Error::other(
                    "benchmark Pump market unexpectedly carried PumpSwap reserve context",
                ));
            }
            None => {
                return Err(io::Error::other(
                    "benchmark snapshot missing reserve-aware FL2 state",
                ));
            }
        };
        let lifecycle = snapshot
            .last_lifecycle_event
            .as_ref()
            .ok_or_else(|| io::Error::other("benchmark snapshot missing lifecycle-aware FL2 state"))?;
        let lifecycle_checksum = lifecycle.slot
            ^ u64::try_from(lifecycle.detected_at_unix_ms)
                .map_err(|_| io::Error::other("benchmark lifecycle timestamp is negative"))?
                .rotate_left(23);

        snapshot_checksum = snapshot_checksum
            .wrapping_mul(1_099_511_628_211)
            .wrapping_add(snapshot.last_sequence.unwrap_or(0))
            ^ one_second.net_quote_quantity.to_bits()
            ^ one_second.quote_flow_acceleration_per_second2.to_bits().rotate_left(17)
            ^ reserve_checksum.rotate_left(31)
            ^ lifecycle_checksum;
        black_box(snapshot_checksum);

        next_sequence = next_sequence
            .checked_add(1)
            .ok_or_else(|| io::Error::other("benchmark sequence overflow"))?;
        next_observed_at_unix_ms = next_observed_at_unix_ms
            .checked_add(1)
            .ok_or_else(|| io::Error::other("benchmark observation timestamp overflow"))?;
    }

    Ok(FastStateBenchmarkReport {
        active_markets,
        burst_events,
        state_update_samples,
        events_per_second,
        apply_latency: latency_summary(apply_samples)?,
        state_update_latency: latency_summary(state_update_latencies)?,
        rss_before_bytes,
        rss_after_state_init_bytes,
        rss_state_init_delta_bytes,
        rss_bytes_per_active_market,
        rss_after_burst_bytes,
        snapshot_checksum,
    })
}

fn benchmark_market(index: usize) -> io::Result<FastMarketKey> {
    FastMarketKey::new(
        format!("BenchmarkMint{index:016}"),
        WSOL_MINT,
        VenueId::PumpFunBondingCurve,
    )
    .map_err(|error| io::Error::other(error.to_string()))
}

fn benchmark_lifecycle_event(
    index: usize,
    market: &FastMarketKey,
    slot: u64,
    detected_at_unix_ms: i64,
) -> TokenLifecycleEvent {
    TokenLifecycleEvent {
        kind: LifecycleEventKind::PumpGraduation,
        provider: ProviderId::SolanaPublic,
        mint: market.mint.clone(),
        quote_mint: market.quote_mint.clone(),
        from_venue: VenueId::PumpFunBondingCurve,
        to_venue: VenueId::PumpSwap,
        pool_address: format!("BenchmarkPool{index:016}"),
        signature: format!("benchmark-graduation-{index}"),
        slot,
        detected_at_unix_ms,
        occurred_at_unix_ms: Some(detected_at_unix_ms),
    }
}

fn benchmark_event(
    sequence: u64,
    market: FastMarketKey,
    observed_at_unix_ms: i64,
) -> io::Result<FastEvent> {
    let kind = if sequence % 3 == 0 {
        FastEventKind::Sell
    } else {
        FastEventKind::Buy
    };
    let quote_quantity = 1.0 + (sequence % 17) as f64 / 10.0;
    let base_quantity = 100.0 + (sequence % 29) as f64;
    let price_quote = quote_quantity / base_quantity;
    let reserve_offset = sequence % 1_000_000;

    let event = FastEvent::new(
        FastEventId::new(format!("benchmark-signature-{sequence}"), 0)
            .map_err(|error| io::Error::other(error.to_string()))?,
        sequence,
        ProviderId::SolanaPublic,
        market,
        kind,
        Some(format!("benchmark-actor-{}", sequence % 256)),
        sequence,
        observed_at_unix_ms,
        observed_at_unix_ms,
        base_quantity,
        quote_quantity,
        price_quote,
    )
    .map_err(|error| io::Error::other(error.to_string()))?;

    event
        .with_reserve_context(FastReserveContext::PumpCurve {
            virtual_base_reserve_raw: 1_000_000_000_000 + reserve_offset,
            virtual_quote_reserve_raw: 30_000_000_000 + reserve_offset,
            real_base_reserve_raw: 700_000_000_000 + reserve_offset,
            real_quote_reserve_raw: 15_000_000_000 + reserve_offset,
            base_decimals: 6,
            quote_decimals: 9,
        })
        .map_err(|error| io::Error::other(error.to_string()))
}

fn latency_summary(mut samples: Vec<u128>) -> io::Result<LatencySummary> {
    if samples.is_empty() {
        return Err(io::Error::other("benchmark latency sample set was empty"));
    }
    samples.sort_unstable();
    Ok(LatencySummary {
        p50_ns: percentile(&samples, 50),
        p95_ns: percentile(&samples, 95),
        p99_ns: percentile(&samples, 99),
        max_ns: *samples.last().expect("non-empty samples checked above"),
    })
}

fn percentile(sorted: &[u128], percent: usize) -> u128 {
    let rank = percent.saturating_mul(sorted.len()).div_ceil(100);
    sorted[rank.saturating_sub(1).min(sorted.len() - 1)]
}

fn rss_bytes() -> io::Result<Option<u64>> {
    let status = match fs::read_to_string("/proc/self/status") {
        Ok(status) => status,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };
    let Some(line) = status.lines().find(|line| line.starts_with("VmRSS:")) else {
        return Ok(None);
    };
    let mut fields = line.split_whitespace();
    let _label = fields.next();
    let value_kib = fields
        .next()
        .ok_or_else(|| io::Error::other("VmRSS line is missing a numeric value"))?
        .parse::<u64>()
        .map_err(|error| io::Error::other(format!("invalid VmRSS value: {error}")))?;
    let unit = fields.next().unwrap_or("kB");
    if unit != "kB" {
        return Err(io::Error::other(format!(
            "unsupported VmRSS unit '{unit}'"
        )));
    }
    value_kib
        .checked_mul(1_024)
        .map(Some)
        .ok_or_else(|| io::Error::other("VmRSS byte conversion overflow"))
}

fn option_delta(before: Option<u64>, after: Option<u64>) -> Option<u64> {
    match (before, after) {
        (Some(before), Some(after)) => Some(after.saturating_sub(before)),
        _ => None,
    }
}

fn required_argument(
    args: &mut impl Iterator<Item = OsString>,
    program: &OsString,
    name: &str,
) -> io::Result<OsString> {
    args.next()
        .ok_or_else(|| io::Error::other(format!("missing {name}; {}", usage(program))))
}

fn parse_positive_usize(value: OsString, field: &str) -> io::Result<usize> {
    let value = value
        .into_string()
        .map_err(|_| io::Error::other(format!("{field} must be valid UTF-8 decimal text")))?;
    let parsed = value
        .parse::<usize>()
        .map_err(|error| io::Error::other(format!("invalid {field} '{value}': {error}")))?;
    if parsed == 0 {
        return Err(io::Error::other(format!(
            "{field} must be greater than zero"
        )));
    }
    Ok(parsed)
}

fn usage(program: &OsString) -> String {
    format!(
        "usage: {} fast-state-benchmark <active_markets> <burst_events> <state_update_samples>",
        program.to_string_lossy()
    )
}

fn print_report(report: &FastStateBenchmarkReport) {
    println!("benchmark_version={BENCHMARK_VERSION}");
    println!("state_shape={BENCHMARK_STATE_SHAPE}");
    println!("active_markets={}", report.active_markets);
    println!("burst_events={}", report.burst_events);
    println!("state_update_samples={}", report.state_update_samples);
    println!("events_per_second={:.3}", report.events_per_second);
    print_latency("apply_latency", &report.apply_latency);
    print_latency("state_update_latency", &report.state_update_latency);
    println!("rss_before_bytes={}", option_u64(report.rss_before_bytes));
    println!(
        "rss_after_state_init_bytes={}",
        option_u64(report.rss_after_state_init_bytes)
    );
    println!(
        "rss_state_init_delta_bytes={}",
        option_u64(report.rss_state_init_delta_bytes)
    );
    println!(
        "rss_bytes_per_active_market={}",
        option_u64(report.rss_bytes_per_active_market)
    );
    println!(
        "rss_after_burst_bytes={}",
        option_u64(report.rss_after_burst_bytes)
    );
    println!("snapshot_checksum={}", report.snapshot_checksum);
}

fn print_latency(prefix: &str, latency: &LatencySummary) {
    println!("{prefix}_p50_ns={}", latency.p50_ns);
    println!("{prefix}_p95_ns={}", latency.p95_ns);
    println!("{prefix}_p99_ns={}", latency.p99_ns);
    println!("{prefix}_max_ns={}", latency.max_ns);
}

fn option_u64(value: Option<u64>) -> String {
    value
        .map(|value| value.to_string())
        .unwrap_or_else(|| "none".to_owned())
}
