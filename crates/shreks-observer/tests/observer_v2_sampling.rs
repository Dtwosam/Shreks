#[path = "../src/bin/observer_v2/sampling.rs"]
mod sampling;

use shreks_core::{PairMarketData, ProviderId, TransactionWindow, VenueId};
use sampling::{
    representative_sample, ActivityClass, RepresentativeSample, SamplingPolicy, SamplingRegistry,
    TrackedCandidate,
};

const SECOND: i64 = 1_000;
const MINUTE: i64 = 60 * SECOND;
const HOUR: i64 = 60 * MINUTE;

fn pair(
    provider: ProviderId,
    pair_address: &str,
    observed_at: i64,
    price: &str,
    liquidity: Option<f64>,
) -> PairMarketData {
    PairMarketData {
        provider,
        venue: VenueId::PumpSwap,
        chain_id: "solana".to_owned(),
        dex_id: "pump".to_owned(),
        pair_address: pair_address.to_owned(),
        base_mint: "mint-a".to_owned(),
        base_name: None,
        base_symbol: None,
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: None,
        quote_symbol: None,
        price_native: None,
        price_usd: Some(price.to_owned()),
        liquidity_usd: liquidity,
        volume_5m: Some(100.0),
        volume_1h: None,
        volume_6h: None,
        volume_24h: None,
        transactions: vec![TransactionWindow {
            window: "m5".to_owned(),
            buys: 10,
            sells: 5,
        }],
        fdv_usd: None,
        market_cap_usd: None,
        pair_created_at_unix_ms: Some(0),
        observed_at_unix_ms: observed_at,
    }
}

fn sample(at: i64, price: f64) -> RepresentativeSample {
    RepresentativeSample {
        provider: ProviderId::DexScreener,
        pair_address: "pair-a".to_owned(),
        observed_at_unix_ms: at,
        price_usd: price,
        liquidity_usd: Some(100_000.0),
        volume_m5_usd: Some(10_000.0),
        buys_m5: Some(10),
        sells_m5: Some(5),
    }
}

#[test]
fn default_policy_has_expected_age_bands() {
    let policy = SamplingPolicy::default_v1();

    assert_eq!(policy.interval_ms(0, ActivityClass::Calm), 10 * SECOND);
    assert_eq!(
        policy.interval_ms(15 * MINUTE, ActivityClass::Calm),
        10 * SECOND
    );
    assert_eq!(
        policy.interval_ms(15 * MINUTE + 1, ActivityClass::Calm),
        30 * SECOND
    );
    assert_eq!(policy.interval_ms(HOUR, ActivityClass::Calm), 30 * SECOND);
    assert_eq!(
        policy.interval_ms(HOUR + 1, ActivityClass::Calm),
        60 * SECOND
    );
    assert_eq!(policy.interval_ms(4 * HOUR, ActivityClass::Calm), 60 * SECOND);
    assert_eq!(
        policy.interval_ms(4 * HOUR + 1, ActivityClass::Calm),
        300 * SECOND
    );
    assert_eq!(policy.interval_ms(24 * HOUR, ActivityClass::Calm), 300 * SECOND);
}

#[test]
fn activity_boosts_sampling_but_never_below_five_seconds() {
    let policy = SamplingPolicy::default_v1();

    assert_eq!(policy.interval_ms(30 * MINUTE, ActivityClass::Active), 15 * SECOND);
    assert_eq!(policy.interval_ms(30 * MINUTE, ActivityClass::Hot), 7_500);
    assert_eq!(policy.interval_ms(1 * MINUTE, ActivityClass::Active), 5 * SECOND);
    assert_eq!(policy.interval_ms(1 * MINUTE, ActivityClass::Hot), 5 * SECOND);
}

#[test]
fn repeated_total_provider_failure_backs_off_and_is_bounded() {
    let policy = SamplingPolicy::default_v1();
    let mut candidate = TrackedCandidate::new(1, "mint-a".to_owned(), 0).unwrap();

    candidate.schedule_after_failure(60 * SECOND, &policy);
    assert_eq!(candidate.consecutive_failures, 1);
    assert_eq!(candidate.next_due_at_unix_ms, 80 * SECOND);

    candidate.schedule_after_failure(80 * SECOND, &policy);
    assert_eq!(candidate.consecutive_failures, 2);
    assert_eq!(candidate.next_due_at_unix_ms, 120 * SECOND);

    for _ in 0..20 {
        let now = candidate.next_due_at_unix_ms;
        candidate.schedule_after_failure(now, &policy);
    }
    assert!(candidate.next_due_at_unix_ms <= 24 * HOUR);
    let final_gap = candidate.next_due_at_unix_ms - (candidate.last_schedule_anchor_unix_ms);
    assert_eq!(final_gap, 300 * SECOND);
}

#[test]
fn pump_then_dump_path_preserves_extrema_and_times() {
    let mut candidate = TrackedCandidate::new(1, "mint-a".to_owned(), 0).unwrap();

    assert_eq!(candidate.record_sample(sample(0, 100.0)).unwrap(), ActivityClass::Calm);
    assert_eq!(candidate.record_sample(sample(10_000, 400.0)).unwrap(), ActivityClass::Hot);
    assert_eq!(candidate.record_sample(sample(20_000, 60.0)).unwrap(), ActivityClass::Hot);

    assert_eq!(candidate.first_price_usd, Some(100.0));
    assert_eq!(candidate.high_price_usd, Some(400.0));
    assert_eq!(candidate.high_at_unix_ms, Some(10_000));
    assert_eq!(candidate.low_price_usd, Some(60.0));
    assert_eq!(candidate.low_at_unix_ms, Some(20_000));
    assert!((candidate.mfe_pct().unwrap() - 300.0).abs() < 1e-9);
    assert!((candidate.mae_pct().unwrap() + 40.0).abs() < 1e-9);
}

#[test]
fn representative_pair_is_deterministic_and_prefers_liquidity() {
    let snapshots = vec![
        pair(ProviderId::Meteora, "pair-z", 10, "1.0", Some(50_000.0)),
        pair(ProviderId::DexScreener, "pair-b", 10, "1.1", Some(100_000.0)),
        pair(ProviderId::DexScreener, "pair-a", 10, "1.2", Some(100_000.0)),
    ];

    let selected = representative_sample(&snapshots).unwrap();
    assert_eq!(selected.provider, ProviderId::DexScreener);
    assert_eq!(selected.pair_address, "pair-a");
    assert_eq!(selected.price_usd, 1.2);

    let mut reversed = snapshots;
    reversed.reverse();
    assert_eq!(representative_sample(&reversed).unwrap(), selected);
}

#[test]
fn representative_pair_rejects_unusable_prices() {
    let snapshots = vec![
        pair(ProviderId::DexScreener, "zero", 10, "0", Some(1_000_000.0)),
        pair(ProviderId::DexScreener, "negative", 10, "-1", Some(1_000_000.0)),
        pair(ProviderId::DexScreener, "nan", 10, "NaN", Some(1_000_000.0)),
        pair(ProviderId::DexScreener, "inf", 10, "inf", Some(1_000_000.0)),
        pair(ProviderId::DexScreener, "bad", 10, "abc", Some(1_000_000.0)),
    ];

    assert!(representative_sample(&snapshots).is_none());
}

#[test]
fn registry_round_trip_is_canonical_and_preserves_path_state() {
    let mut left = SamplingRegistry::default();
    let mut a = TrackedCandidate::new(2, "mint-b".to_owned(), 20).unwrap();
    a.record_sample(sample(100, 10.0)).unwrap();
    a.record_sample(sample(200, 15.0)).unwrap();
    a.next_due_at_unix_ms = 250;
    left.register(a).unwrap();

    let mut b = TrackedCandidate::new(1, "mint-a".to_owned(), 10).unwrap();
    b.record_sample(sample(100, 100.0)).unwrap();
    b.record_sample(sample(150, 80.0)).unwrap();
    b.next_due_at_unix_ms = 200;
    left.register(b).unwrap();

    let encoded = left.encode();
    let decoded = SamplingRegistry::decode(&encoded).unwrap();
    assert_eq!(decoded, left);

    let mut right = SamplingRegistry::default();
    for candidate in left.candidates().iter().rev().cloned() {
        right.register(candidate).unwrap();
    }
    assert_eq!(right.encode(), encoded);
}

#[test]
fn corrupt_registry_fails_closed() {
    assert!(SamplingRegistry::decode("wrong-version\n").is_err());
    assert!(SamplingRegistry::decode("a10-registry-v1\nnot|enough|fields").is_err());
}

#[test]
fn due_order_is_deterministic_and_retention_has_24h_grace() {
    let policy = SamplingPolicy::default_v1();
    let mut registry = SamplingRegistry::default();

    let mut late = TrackedCandidate::new(2, "mint-b".to_owned(), 10).unwrap();
    late.next_due_at_unix_ms = 200;
    registry.register(late).unwrap();

    let mut first = TrackedCandidate::new(1, "mint-a".to_owned(), 0).unwrap();
    first.next_due_at_unix_ms = 100;
    registry.register(first).unwrap();

    assert_eq!(
        registry
            .due_candidates(200)
            .into_iter()
            .map(|candidate| candidate.candidate_id)
            .collect::<Vec<_>>(),
        vec![1, 2]
    );

    registry.expire(24 * HOUR + 9 * MINUTE, &policy);
    assert_eq!(registry.len(), 2);
    registry.expire(24 * HOUR + 10 * MINUTE + 11, &policy);
    assert_eq!(registry.len(), 1);
    registry.expire(24 * HOUR + 10 * MINUTE + 21, &policy);
    assert!(registry.is_empty());
}
