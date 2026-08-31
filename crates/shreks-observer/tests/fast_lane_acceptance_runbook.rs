const RUNBOOK: &str =
    include_str!("../../../docs/operations/FL1_FAST_LANE_ACCEPTANCE.md");

#[test]
fn fl1_acceptance_runbook_preserves_read_only_and_release_boundaries() {
    for required in [
        "LIVE TRADING: DISABLED",
        "/opt/shreks/current",
        "RELEASE_MANIFEST.json",
        "/var/lib/shreks/shreks.db",
        "target/release/shreks-observe",
        "fast-lane-acceptance",
        "systemctl show shreks-observe.service",
        "NRestarts",
        "journalctl -u shreks-observe.service",
        "ps -p",
        "free -h",
        "df -h",
        "stat -c",
        "sequence_integrity_violations=0",
        "pump_raw_events > 0",
        "pumpswap_raw_events > 0",
        "Do not advance to FL2",
        "read-only",
    ] {
        assert!(
            RUNBOOK.contains(required),
            "FL1.5 production runbook must contain required acceptance evidence: {required}"
        );
    }

    for forbidden in [
        "/target/release/shreks-fast-lane-acceptance",
        "systemctl restart shreks-observe",
        "systemctl stop shreks-observe",
        "systemctl kill shreks-observe",
        "send_transaction",
        "enable live",
        "LIVE TRADING: ENABLED",
    ] {
        assert!(
            !RUNBOOK.contains(forbidden),
            "FL1.5 routine acceptance must not add incompatible release paths, mutation, or capital authority: {forbidden}"
        );
    }
}

#[test]
fn fl1_acceptance_runbook_distinguishes_database_and_host_only_evidence() {
    for required in [
        "Database-backed evidence",
        "Host-only evidence",
        "attempted duplicate",
        "CPU",
        "RSS",
        "public-RPC/reconnect",
        "DB/WAL growth",
        "CI is necessary but insufficient",
    ] {
        assert!(RUNBOOK.contains(required), "missing evidence boundary: {required}");
    }
}

#[test]
fn fl1_acceptance_runbook_covers_quarantine_integrity_and_zero_cost_provider_contract() {
    for required in [
        "pump_conflict_quarantine_total",
        "pumpswap_conflict_quarantine_total",
        "pump_conflict_quarantine_events",
        "pumpswap_conflict_quarantine_events",
        "canonical_conflict_quarantine_violations=0",
        "solana_public",
        "official public Solana",
        "paid provider",
        "isolated quarantined fork conflicts",
        "persistent or growing quarantine",
    ] {
        assert!(
            RUNBOOK.contains(required),
            "FL1.5 runbook must document quarantine/public-provider acceptance contract: {required}"
        );
    }

    for forbidden in [
        "Helius -> Chainstack -> Alchemy",
        "proves continued `chainstack` raw/canonical progress",
        "proves continued `alchemy` raw/canonical progress",
    ] {
        assert!(
            !RUNBOOK.contains(forbidden),
            "FL1.5 runbook must not retain the superseded metered-provider realtime contract: {forbidden}"
        );
    }
}
