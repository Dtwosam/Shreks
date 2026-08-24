use std::{error::Error, fmt};

use shreks_core::{PairMarketData, ProviderId};

const SECOND_MS: i64 = 1_000;
const MINUTE_MS: i64 = 60 * SECOND_MS;
const HOUR_MS: i64 = 60 * MINUTE_MS;
const REGISTRY_VERSION: &str = "a10-registry-v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ActivityClass {
    Calm,
    Active,
    Hot,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SamplingPolicy {
    min_interval_ms: i64,
    early_interval_ms: i64,
    first_hour_interval_ms: i64,
    first_four_hours_interval_ms: i64,
    late_interval_ms: i64,
    retention_horizon_ms: i64,
    retention_grace_ms: i64,
    active_price_change_pct: f64,
    hot_price_change_pct: f64,
    active_liquidity_change_pct: f64,
    hot_liquidity_change_pct: f64,
    active_volume_change_pct: f64,
    hot_volume_change_pct: f64,
    active_transaction_change_pct: f64,
    hot_transaction_change_pct: f64,
}

impl SamplingPolicy {
    pub fn default_v1() -> Self {
        Self {
            min_interval_ms: 5 * SECOND_MS,
            early_interval_ms: 10 * SECOND_MS,
            first_hour_interval_ms: 30 * SECOND_MS,
            first_four_hours_interval_ms: 60 * SECOND_MS,
            late_interval_ms: 300 * SECOND_MS,
            retention_horizon_ms: 24 * HOUR_MS,
            retention_grace_ms: 10 * MINUTE_MS,
            active_price_change_pct: 5.0,
            hot_price_change_pct: 20.0,
            active_liquidity_change_pct: 10.0,
            hot_liquidity_change_pct: 25.0,
            active_volume_change_pct: 25.0,
            hot_volume_change_pct: 100.0,
            active_transaction_change_pct: 25.0,
            hot_transaction_change_pct: 100.0,
        }
    }

    pub fn interval_ms(&self, age_ms: i64, activity: ActivityClass) -> i64 {
        let age_ms = age_ms.max(0);
        let base = if age_ms <= 15 * MINUTE_MS {
            self.early_interval_ms
        } else if age_ms <= HOUR_MS {
            self.first_hour_interval_ms
        } else if age_ms <= 4 * HOUR_MS {
            self.first_four_hours_interval_ms
        } else {
            self.late_interval_ms
        };

        let adjusted = match activity {
            ActivityClass::Calm => base,
            ActivityClass::Active => base / 2,
            ActivityClass::Hot => base / 4,
        };
        adjusted.max(self.min_interval_ms)
    }

    pub fn retention_deadline_unix_ms(&self, discovered_at_unix_ms: i64) -> i64 {
        discovered_at_unix_ms
            .saturating_add(self.retention_horizon_ms)
            .saturating_add(self.retention_grace_ms)
    }

    fn failure_interval_ms(&self, age_ms: i64, consecutive_failures: u32) -> i64 {
        let base = self.interval_ms(age_ms, ActivityClass::Calm);
        let shift = consecutive_failures.min(31);
        let multiplier = 1_i64.checked_shl(shift).unwrap_or(i64::MAX);
        base.saturating_mul(multiplier).min(self.late_interval_ms)
    }

    fn classify_changes(
        &self,
        price_change_pct: Option<f64>,
        liquidity_change_pct: Option<f64>,
        volume_change_pct: Option<f64>,
        transaction_change_pct: Option<f64>,
    ) -> ActivityClass {
        if threshold_hit(price_change_pct, self.hot_price_change_pct)
            || threshold_hit(liquidity_change_pct, self.hot_liquidity_change_pct)
            || threshold_hit(volume_change_pct, self.hot_volume_change_pct)
            || threshold_hit(transaction_change_pct, self.hot_transaction_change_pct)
        {
            ActivityClass::Hot
        } else if threshold_hit(price_change_pct, self.active_price_change_pct)
            || threshold_hit(liquidity_change_pct, self.active_liquidity_change_pct)
            || threshold_hit(volume_change_pct, self.active_volume_change_pct)
            || threshold_hit(transaction_change_pct, self.active_transaction_change_pct)
        {
            ActivityClass::Active
        } else {
            ActivityClass::Calm
        }
    }
}

impl Default for SamplingPolicy {
    fn default() -> Self {
        Self::default_v1()
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct RepresentativeSample {
    pub provider: ProviderId,
    pub pair_address: String,
    pub observed_at_unix_ms: i64,
    pub price_usd: f64,
    pub liquidity_usd: Option<f64>,
    pub volume_m5_usd: Option<f64>,
    pub buys_m5: Option<u64>,
    pub sells_m5: Option<u64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TrackedCandidate {
    pub candidate_id: i64,
    pub mint: String,
    pub discovered_at_unix_ms: i64,
    pub last_sample_at_unix_ms: Option<i64>,
    pub next_due_at_unix_ms: i64,
    pub last_schedule_anchor_unix_ms: i64,
    pub consecutive_failures: u32,
    pub first_price_usd: Option<f64>,
    pub last_price_usd: Option<f64>,
    pub high_price_usd: Option<f64>,
    pub high_at_unix_ms: Option<i64>,
    pub low_price_usd: Option<f64>,
    pub low_at_unix_ms: Option<i64>,
    pub last_liquidity_usd: Option<f64>,
    pub last_volume_m5_usd: Option<f64>,
    pub last_buys_m5: Option<u64>,
    pub last_sells_m5: Option<u64>,
}

impl TrackedCandidate {
    pub fn new(
        candidate_id: i64,
        mint: String,
        discovered_at_unix_ms: i64,
    ) -> Result<Self, SamplingError> {
        if candidate_id <= 0 {
            return Err(SamplingError::InvalidData(
                "candidate_id must be positive".to_owned(),
            ));
        }
        if mint.trim().is_empty() {
            return Err(SamplingError::InvalidData(
                "candidate mint must not be empty".to_owned(),
            ));
        }
        if discovered_at_unix_ms < 0 {
            return Err(SamplingError::InvalidData(
                "candidate discovery timestamp must be nonnegative".to_owned(),
            ));
        }

        Ok(Self {
            candidate_id,
            mint,
            discovered_at_unix_ms,
            last_sample_at_unix_ms: None,
            next_due_at_unix_ms: discovered_at_unix_ms,
            last_schedule_anchor_unix_ms: discovered_at_unix_ms,
            consecutive_failures: 0,
            first_price_usd: None,
            last_price_usd: None,
            high_price_usd: None,
            high_at_unix_ms: None,
            low_price_usd: None,
            low_at_unix_ms: None,
            last_liquidity_usd: None,
            last_volume_m5_usd: None,
            last_buys_m5: None,
            last_sells_m5: None,
        })
    }

    pub fn record_sample(
        &mut self,
        sample: RepresentativeSample,
    ) -> Result<ActivityClass, SamplingError> {
        validate_sample(&sample)?;
        if sample.observed_at_unix_ms < self.discovered_at_unix_ms {
            return Err(SamplingError::InvalidData(
                "sample predates candidate discovery".to_owned(),
            ));
        }
        if self
            .last_sample_at_unix_ms
            .is_some_and(|last| sample.observed_at_unix_ms < last)
        {
            return Err(SamplingError::InvalidData(
                "sample timestamp moved backward".to_owned(),
            ));
        }

        let activity = match self.last_price_usd {
            None => ActivityClass::Calm,
            Some(previous_price) => {
                let price_change = relative_abs_change_pct(previous_price, sample.price_usd);
                let liquidity_change = relative_optional_change_pct(
                    self.last_liquidity_usd,
                    sample.liquidity_usd,
                );
                let volume_change = relative_optional_change_pct(
                    self.last_volume_m5_usd,
                    sample.volume_m5_usd,
                );
                let old_transactions = optional_sum(self.last_buys_m5, self.last_sells_m5);
                let new_transactions = optional_sum(sample.buys_m5, sample.sells_m5);
                let transaction_change = relative_optional_count_change_pct(
                    old_transactions,
                    new_transactions,
                );
                SamplingPolicy::default_v1().classify_changes(
                    Some(price_change),
                    liquidity_change,
                    volume_change,
                    transaction_change,
                )
            }
        };

        if self.first_price_usd.is_none() {
            self.first_price_usd = Some(sample.price_usd);
        }
        if self.high_price_usd.is_none_or(|high| sample.price_usd > high) {
            self.high_price_usd = Some(sample.price_usd);
            self.high_at_unix_ms = Some(sample.observed_at_unix_ms);
        }
        if self.low_price_usd.is_none_or(|low| sample.price_usd < low) {
            self.low_price_usd = Some(sample.price_usd);
            self.low_at_unix_ms = Some(sample.observed_at_unix_ms);
        }

        self.last_sample_at_unix_ms = Some(sample.observed_at_unix_ms);
        self.last_price_usd = Some(sample.price_usd);
        self.last_liquidity_usd = sample.liquidity_usd;
        self.last_volume_m5_usd = sample.volume_m5_usd;
        self.last_buys_m5 = sample.buys_m5;
        self.last_sells_m5 = sample.sells_m5;
        Ok(activity)
    }

    pub fn schedule_after_success(
        &mut self,
        now_unix_ms: i64,
        policy: &SamplingPolicy,
        activity: ActivityClass,
    ) {
        self.consecutive_failures = 0;
        self.last_schedule_anchor_unix_ms = now_unix_ms;
        let age_ms = now_unix_ms.saturating_sub(self.discovered_at_unix_ms);
        self.next_due_at_unix_ms = now_unix_ms.saturating_add(policy.interval_ms(age_ms, activity));
    }

    pub fn schedule_after_failure(&mut self, now_unix_ms: i64, policy: &SamplingPolicy) {
        self.consecutive_failures = self.consecutive_failures.saturating_add(1);
        self.last_schedule_anchor_unix_ms = now_unix_ms;
        let age_ms = now_unix_ms.saturating_sub(self.discovered_at_unix_ms);
        let interval = policy.failure_interval_ms(age_ms, self.consecutive_failures);
        self.next_due_at_unix_ms = now_unix_ms.saturating_add(interval);
    }

    pub fn mfe_pct(&self) -> Option<f64> {
        percentage_change(self.high_price_usd?, self.first_price_usd?)
    }

    pub fn mae_pct(&self) -> Option<f64> {
        percentage_change(self.low_price_usd?, self.first_price_usd?)
    }

    fn validate_restored(&self) -> Result<(), SamplingError> {
        if self.candidate_id <= 0 || self.mint.trim().is_empty() || self.discovered_at_unix_ms < 0 {
            return Err(SamplingError::InvalidData(
                "restored candidate identity is invalid".to_owned(),
            ));
        }
        if self.next_due_at_unix_ms < 0 || self.last_schedule_anchor_unix_ms < 0 {
            return Err(SamplingError::InvalidData(
                "restored candidate schedule is invalid".to_owned(),
            ));
        }
        for (name, value) in [
            ("first_price_usd", self.first_price_usd),
            ("last_price_usd", self.last_price_usd),
            ("high_price_usd", self.high_price_usd),
            ("low_price_usd", self.low_price_usd),
        ] {
            if value.is_some_and(|value| !value.is_finite() || value <= 0.0) {
                return Err(SamplingError::InvalidData(format!(
                    "restored {name} must be finite and positive"
                )));
            }
        }
        for (name, value) in [
            ("last_liquidity_usd", self.last_liquidity_usd),
            ("last_volume_m5_usd", self.last_volume_m5_usd),
        ] {
            if value.is_some_and(|value| !value.is_finite() || value < 0.0) {
                return Err(SamplingError::InvalidData(format!(
                    "restored {name} must be finite and nonnegative"
                )));
            }
        }
        if self.high_price_usd.is_some() != self.high_at_unix_ms.is_some()
            || self.low_price_usd.is_some() != self.low_at_unix_ms.is_some()
        {
            return Err(SamplingError::InvalidData(
                "restored path extrema require matching timestamps".to_owned(),
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct SamplingRegistry {
    candidates: Vec<TrackedCandidate>,
}

impl SamplingRegistry {
    pub fn register(&mut self, candidate: TrackedCandidate) -> Result<(), SamplingError> {
        candidate.validate_restored()?;
        if let Some(existing) = self
            .candidates
            .iter_mut()
            .find(|existing| existing.candidate_id == candidate.candidate_id)
        {
            if existing.mint != candidate.mint {
                return Err(SamplingError::InvalidData(format!(
                    "candidate id {} is already registered for a different mint",
                    candidate.candidate_id
                )));
            }
            if *existing != candidate {
                return Err(SamplingError::InvalidData(format!(
                    "candidate id {} is already registered with different state",
                    candidate.candidate_id
                )));
            }
            return Ok(());
        }
        if self
            .candidates
            .iter()
            .any(|existing| existing.mint == candidate.mint)
        {
            return Err(SamplingError::InvalidData(format!(
                "candidate mint {} is already registered under another id",
                candidate.mint
            )));
        }
        self.candidates.push(candidate);
        self.sort_canonical();
        Ok(())
    }

    pub fn candidates(&self) -> &[TrackedCandidate] {
        &self.candidates
    }

    pub fn get_mut(&mut self, candidate_id: i64) -> Option<&mut TrackedCandidate> {
        self.candidates
            .iter_mut()
            .find(|candidate| candidate.candidate_id == candidate_id)
    }

    pub fn contains_candidate_id(&self, candidate_id: i64) -> bool {
        self.candidates
            .iter()
            .any(|candidate| candidate.candidate_id == candidate_id)
    }

    pub fn due_candidates(&self, now_unix_ms: i64) -> Vec<TrackedCandidate> {
        let mut due = self
            .candidates
            .iter()
            .filter(|candidate| candidate.next_due_at_unix_ms <= now_unix_ms)
            .cloned()
            .collect::<Vec<_>>();
        due.sort_by(|left, right| {
            (
                left.next_due_at_unix_ms,
                left.discovered_at_unix_ms,
                left.candidate_id,
                left.mint.as_str(),
            )
                .cmp(&(
                    right.next_due_at_unix_ms,
                    right.discovered_at_unix_ms,
                    right.candidate_id,
                    right.mint.as_str(),
                ))
        });
        due
    }

    pub fn expire(&mut self, now_unix_ms: i64, policy: &SamplingPolicy) {
        self.candidates.retain(|candidate| {
            now_unix_ms <= policy.retention_deadline_unix_ms(candidate.discovered_at_unix_ms)
        });
    }

    pub fn len(&self) -> usize {
        self.candidates.len()
    }

    pub fn is_empty(&self) -> bool {
        self.candidates.is_empty()
    }

    pub fn encode(&self) -> String {
        let mut ordered = self.candidates.clone();
        ordered.sort_by(canonical_candidate_order);
        let mut output = String::from(REGISTRY_VERSION);
        output.push('\n');
        for candidate in ordered {
            output.push_str(&encode_candidate(&candidate));
            output.push('\n');
        }
        output
    }

    pub fn decode(encoded: &str) -> Result<Self, SamplingError> {
        let mut lines = encoded.lines();
        if lines.next() != Some(REGISTRY_VERSION) {
            return Err(SamplingError::InvalidData(
                "unsupported Observer V2 registry version".to_owned(),
            ));
        }

        let mut registry = Self::default();
        for line in lines {
            if line.is_empty() {
                continue;
            }
            registry.register(decode_candidate(line)?)?;
        }
        Ok(registry)
    }

    fn sort_canonical(&mut self) {
        self.candidates.sort_by(canonical_candidate_order);
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SamplingError {
    InvalidData(String),
}

impl fmt::Display for SamplingError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidData(message) => formatter.write_str(message),
        }
    }
}

impl Error for SamplingError {}

pub fn representative_sample(snapshots: &[PairMarketData]) -> Option<RepresentativeSample> {
    let mut best: Option<(f64, String, String, RepresentativeSample)> = None;

    for snapshot in snapshots {
        let price = snapshot
            .price_usd
            .as_deref()
            .and_then(|value| value.parse::<f64>().ok())
            .filter(|value| value.is_finite() && *value > 0.0)?;
        let liquidity = snapshot
            .liquidity_usd
            .filter(|value| value.is_finite() && *value >= 0.0);
        let volume = snapshot
            .volume_5m
            .filter(|value| value.is_finite() && *value >= 0.0);
        let m5 = snapshot.transactions.iter().find(|window| window.window == "m5");
        let sample = RepresentativeSample {
            provider: snapshot.provider,
            pair_address: snapshot.pair_address.clone(),
            observed_at_unix_ms: snapshot.observed_at_unix_ms,
            price_usd: price,
            liquidity_usd: liquidity,
            volume_m5_usd: volume,
            buys_m5: m5.map(|window| window.buys),
            sells_m5: m5.map(|window| window.sells),
        };
        let liquidity_rank = liquidity.unwrap_or(-1.0);
        let provider_key = snapshot.provider.as_str().to_owned();
        let pair_key = snapshot.pair_address.clone();

        let replace = match &best {
            None => true,
            Some((best_liquidity, best_provider, best_pair, _)) => {
                liquidity_rank > *best_liquidity
                    || (liquidity_rank == *best_liquidity
                        && (provider_key.as_str(), pair_key.as_str())
                            < (best_provider.as_str(), best_pair.as_str()))
            }
        };
        if replace {
            best = Some((liquidity_rank, provider_key, pair_key, sample));
        }
    }

    best.map(|(_, _, _, sample)| sample)
}

fn validate_sample(sample: &RepresentativeSample) -> Result<(), SamplingError> {
    if sample.pair_address.trim().is_empty() {
        return Err(SamplingError::InvalidData(
            "representative pair address must not be empty".to_owned(),
        ));
    }
    if sample.observed_at_unix_ms < 0 {
        return Err(SamplingError::InvalidData(
            "representative sample timestamp must be nonnegative".to_owned(),
        ));
    }
    if !sample.price_usd.is_finite() || sample.price_usd <= 0.0 {
        return Err(SamplingError::InvalidData(
            "representative price must be finite and positive".to_owned(),
        ));
    }
    for (name, value) in [
        ("liquidity_usd", sample.liquidity_usd),
        ("volume_m5_usd", sample.volume_m5_usd),
    ] {
        if value.is_some_and(|value| !value.is_finite() || value < 0.0) {
            return Err(SamplingError::InvalidData(format!(
                "representative {name} must be finite and nonnegative"
            )));
        }
    }
    Ok(())
}

fn canonical_candidate_order(left: &TrackedCandidate, right: &TrackedCandidate) -> std::cmp::Ordering {
    (
        left.discovered_at_unix_ms,
        left.candidate_id,
        left.mint.as_str(),
    )
        .cmp(&(
            right.discovered_at_unix_ms,
            right.candidate_id,
            right.mint.as_str(),
        ))
}

fn threshold_hit(value: Option<f64>, threshold: f64) -> bool {
    value.is_some_and(|value| value >= threshold)
}

fn relative_abs_change_pct(old: f64, new: f64) -> f64 {
    if old == 0.0 {
        if new == 0.0 { 0.0 } else { f64::INFINITY }
    } else {
        ((new - old) / old * 100.0).abs()
    }
}

fn relative_optional_change_pct(old: Option<f64>, new: Option<f64>) -> Option<f64> {
    match (old, new) {
        (Some(old), Some(new)) => Some(relative_abs_change_pct(old, new)),
        _ => None,
    }
}

fn optional_sum(left: Option<u64>, right: Option<u64>) -> Option<u64> {
    match (left, right) {
        (Some(left), Some(right)) => Some(left.saturating_add(right)),
        _ => None,
    }
}

fn relative_optional_count_change_pct(old: Option<u64>, new: Option<u64>) -> Option<f64> {
    match (old, new) {
        (Some(old), Some(new)) => Some(relative_abs_change_pct(old as f64, new as f64)),
        _ => None,
    }
}

fn percentage_change(value: f64, baseline: f64) -> Option<f64> {
    if !value.is_finite() || !baseline.is_finite() || baseline <= 0.0 {
        return None;
    }
    let result = (value - baseline) / baseline * 100.0;
    result.is_finite().then_some(result)
}

fn encode_candidate(candidate: &TrackedCandidate) -> String {
    [
        candidate.candidate_id.to_string(),
        encode_hex(candidate.mint.as_bytes()),
        candidate.discovered_at_unix_ms.to_string(),
        encode_optional_i64(candidate.last_sample_at_unix_ms),
        candidate.next_due_at_unix_ms.to_string(),
        candidate.last_schedule_anchor_unix_ms.to_string(),
        candidate.consecutive_failures.to_string(),
        encode_optional_f64(candidate.first_price_usd),
        encode_optional_f64(candidate.last_price_usd),
        encode_optional_f64(candidate.high_price_usd),
        encode_optional_i64(candidate.high_at_unix_ms),
        encode_optional_f64(candidate.low_price_usd),
        encode_optional_i64(candidate.low_at_unix_ms),
        encode_optional_f64(candidate.last_liquidity_usd),
        encode_optional_f64(candidate.last_volume_m5_usd),
        encode_optional_u64(candidate.last_buys_m5),
        encode_optional_u64(candidate.last_sells_m5),
    ]
    .join("|")
}

fn decode_candidate(line: &str) -> Result<TrackedCandidate, SamplingError> {
    let fields = line.split('|').collect::<Vec<_>>();
    if fields.len() != 17 {
        return Err(SamplingError::InvalidData(format!(
            "Observer V2 registry row has {} fields; expected 17",
            fields.len()
        )));
    }

    let candidate_id = parse_i64(fields[0], "candidate_id")?;
    let mint_bytes = decode_hex(fields[1])?;
    let mint = String::from_utf8(mint_bytes).map_err(|_| {
        SamplingError::InvalidData("registry mint is not UTF-8".to_owned())
    })?;
    let discovered_at_unix_ms = parse_i64(fields[2], "discovered_at_unix_ms")?;
    let mut candidate = TrackedCandidate::new(candidate_id, mint, discovered_at_unix_ms)?;
    candidate.last_sample_at_unix_ms = parse_optional_i64(fields[3], "last_sample_at_unix_ms")?;
    candidate.next_due_at_unix_ms = parse_i64(fields[4], "next_due_at_unix_ms")?;
    candidate.last_schedule_anchor_unix_ms = parse_i64(fields[5], "last_schedule_anchor_unix_ms")?;
    candidate.consecutive_failures = fields[6].parse::<u32>().map_err(|error| {
        SamplingError::InvalidData(format!("invalid consecutive_failures: {error}"))
    })?;
    candidate.first_price_usd = parse_optional_f64(fields[7], "first_price_usd")?;
    candidate.last_price_usd = parse_optional_f64(fields[8], "last_price_usd")?;
    candidate.high_price_usd = parse_optional_f64(fields[9], "high_price_usd")?;
    candidate.high_at_unix_ms = parse_optional_i64(fields[10], "high_at_unix_ms")?;
    candidate.low_price_usd = parse_optional_f64(fields[11], "low_price_usd")?;
    candidate.low_at_unix_ms = parse_optional_i64(fields[12], "low_at_unix_ms")?;
    candidate.last_liquidity_usd = parse_optional_f64(fields[13], "last_liquidity_usd")?;
    candidate.last_volume_m5_usd = parse_optional_f64(fields[14], "last_volume_m5_usd")?;
    candidate.last_buys_m5 = parse_optional_u64(fields[15], "last_buys_m5")?;
    candidate.last_sells_m5 = parse_optional_u64(fields[16], "last_sells_m5")?;
    candidate.validate_restored()?;
    Ok(candidate)
}

fn encode_optional_i64(value: Option<i64>) -> String {
    value.map_or_else(|| "~".to_owned(), |value| value.to_string())
}

fn encode_optional_u64(value: Option<u64>) -> String {
    value.map_or_else(|| "~".to_owned(), |value| value.to_string())
}

fn encode_optional_f64(value: Option<f64>) -> String {
    value.map_or_else(
        || "~".to_owned(),
        |value| format!("{:016x}", value.to_bits()),
    )
}

fn parse_i64(value: &str, field: &str) -> Result<i64, SamplingError> {
    value.parse::<i64>().map_err(|error| {
        SamplingError::InvalidData(format!("invalid {field}: {error}"))
    })
}

fn parse_optional_i64(value: &str, field: &str) -> Result<Option<i64>, SamplingError> {
    if value == "~" {
        Ok(None)
    } else {
        parse_i64(value, field).map(Some)
    }
}

fn parse_optional_u64(value: &str, field: &str) -> Result<Option<u64>, SamplingError> {
    if value == "~" {
        Ok(None)
    } else {
        value.parse::<u64>().map(Some).map_err(|error| {
            SamplingError::InvalidData(format!("invalid {field}: {error}"))
        })
    }
}

fn parse_optional_f64(value: &str, field: &str) -> Result<Option<f64>, SamplingError> {
    if value == "~" {
        return Ok(None);
    }
    let bits = u64::from_str_radix(value, 16).map_err(|error| {
        SamplingError::InvalidData(format!("invalid {field} bits: {error}"))
    })?;
    let decoded = f64::from_bits(bits);
    if !decoded.is_finite() {
        return Err(SamplingError::InvalidData(format!(
            "decoded {field} must be finite"
        )));
    }
    Ok(Some(decoded))
}

fn encode_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        output.push(HEX[(byte >> 4) as usize] as char);
        output.push(HEX[(byte & 0x0f) as usize] as char);
    }
    output
}

fn decode_hex(value: &str) -> Result<Vec<u8>, SamplingError> {
    if value.len() % 2 != 0 {
        return Err(SamplingError::InvalidData(
            "registry hex field has odd length".to_owned(),
        ));
    }
    let bytes = value.as_bytes();
    let mut output = Vec::with_capacity(bytes.len() / 2);
    for index in (0..bytes.len()).step_by(2) {
        let high = decode_hex_nibble(bytes[index])?;
        let low = decode_hex_nibble(bytes[index + 1])?;
        output.push((high << 4) | low);
    }
    Ok(output)
}

fn decode_hex_nibble(value: u8) -> Result<u8, SamplingError> {
    match value {
        b'0'..=b'9' => Ok(value - b'0'),
        b'a'..=b'f' => Ok(value - b'a' + 10),
        b'A'..=b'F' => Ok(value - b'A' + 10),
        _ => Err(SamplingError::InvalidData(
            "registry contains invalid hex".to_owned(),
        )),
    }
}
