# Phase G1 Production Paper Evidence Runtime Design

**Phase:** G1 — Dedicated Linux production runtime, first bounded slice  
**Base:** sealed E15 `b8daa24bbaaa1369e91c9735aaad0d990fd6ba53`  
**Date:** 2026-08-25

## Purpose

Turn the already-sealed E15 paper-evidence primitives into an explicit long-running production process that can continuously collect real holder-distribution plus purpose-attributed Jupiter ENTRY/EXIT quote evidence for recently active observer candidates on one Linux host.

This slice exists to make a real observer-backed paper campaign possible. It does not run the Python campaign coordinator yet and does not authorize live trading.

## Non-negotiable authority boundary

The runtime remains inside `shreks-observer`, whose crate-level contract is observe/read-only orchestration. It may:

- read normalized candidate/market state from the operational SQLite database,
- call read-only Helius distribution APIs,
- call read-only Jupiter quote/build APIs,
- persist holder-distribution, exit-quote, and purpose-attributed paper-quote evidence,
- report provider failures and operational counts.

It must not:

- create trade intents,
- construct or sign transactions,
- submit transactions,
- mutate the champion/challenger registry,
- promote candidates,
- invoke E12 promotion,
- enable live mode,
- contain wallet/private-key material.

## 1. Candidate selection

Add one bounded storage read model, `EvidenceProbeCandidate`, and a deterministic `ShreksDb::recent_evidence_probe_candidates(as_of_unix_ms, lookback_ms, limit)` query.

Selection rules:

1. candidate must have at least one `market_snapshots` row at or before `as_of_unix_ms` and inside the requested lookback window;
2. one row is returned per candidate;
3. candidates are ordered by latest eligible market observation descending, then candidate id ascending;
4. the caller supplies a hard `limit`;
5. future market observations are invisible;
6. `limit == 0` returns an empty set without querying providers;
7. invalid negative timestamps or non-positive lookback values fail closed.

This keeps the evidence daemon bounded and point-in-time rather than scanning every historical candidate forever.

## 2. Explicit runtime configuration

Add `PaperEvidenceRuntimeConfig` in `shreks-observer`. It is derived from an environment-like lookup so tests do not mutate process-global state.

Operational parameters may have conservative defaults where they do not change economic semantics. Economic evidence parameters must be explicitly supplied and validated.

Required economic/probe inputs:

- `SHREKS_PAPER_PROBE_POLICY_VERSION`
- `SHREKS_PAPER_QUOTE_ASSET_MINT`
- `SHREKS_PAPER_QUOTE_TAKER`
- `SHREKS_PAPER_ENTRY_INPUT_AMOUNT`
- `SHREKS_PAPER_EXIT_INPUT_AMOUNT`
- `SHREKS_PAPER_SLIPPAGE_BPS`
- `SHREKS_PAPER_DISTRIBUTION_PAGE_SIZE`
- `SHREKS_PAPER_DISTRIBUTION_MAX_PAGES`

Operational inputs:

- `SHREKS_DB_PATH` (same operational database as the observer)
- `SHREKS_PAPER_EVIDENCE_INTERVAL_SECONDS`
- `SHREKS_PAPER_EVIDENCE_LOOKBACK_SECONDS`
- `SHREKS_PAPER_EVIDENCE_MAX_CANDIDATES`

The runtime also requires both `HELIUS_API_KEY` and `JUPITER_API_KEY` through the existing `ProviderConfig`. Missing required providers fail startup rather than silently producing an evidence stream that cannot support E15.

The configuration object exposes `probe_for(candidate_mint)` which constructs one `SafetyEvidenceProbe` with:

- Helius holder-distribution request for the candidate mint,
- EXIT Jupiter quote from candidate mint -> quote asset,
- ENTRY Jupiter quote from quote asset -> candidate mint,
- identical probe version, taker, and slippage attribution for both directions.

No test-fixture threshold or amount becomes a production default.

## 3. Long-running evidence daemon

Add binary `shreks-paper-evidence`.

Startup:

1. parse and validate `PaperEvidenceRuntimeConfig`;
2. build `ProviderConfig`;
3. require Helius and Jupiter;
4. open the shared SQLite WAL database through `ShreksDb`;
5. construct exactly one `SafetyEvidenceCollector` using Helius for distribution and Jupiter for quotes;
6. log only non-secret enablement/config summaries.

Each cycle:

1. capture one cycle `as_of_unix_ms`;
2. ask storage for bounded recent candidates;
3. derive a candidate-specific probe;
4. call the sealed E15 `SafetyEvidenceCollector`;
5. aggregate stored-evidence and provider-failure counts;
6. continue across nonfatal provider failures represented in collector reports;
7. fail the process on storage/config/probe integrity errors rather than hiding evidence corruption.

The process sleeps until the next configured interval and exits cleanly on Ctrl-C/systemd SIGINT handling through Tokio's signal support.

## 4. Restart and duplicate behavior

The daemon stores no private in-memory trading state. Restart safety comes from:

- point-in-time candidate selection from SQLite,
- append/idempotent evidence persistence already sealed in E15,
- deterministic quote identity,
- provider-response identity checks,
- SQLite WAL durability.

A restart may repeat a read-only provider call. Replayed identical evidence must remain idempotent; contradictory evidence identities continue to fail closed through sealed E15 storage semantics.

## 5. Linux supervision

Add production `systemd` templates for the existing `shreks-observe` process and the new `shreks-paper-evidence` process plus a `shreks.target` grouping unit.

Requirements:

- dedicated non-root `shreks` user,
- working directory `/opt/shreks/current`,
- environment file `/etc/shreks/shreks.env`,
- persistent database/evidence paths supplied by environment,
- `Restart=on-failure`,
- startup ordering ensures the filesystem/network are available,
- no secrets are embedded in unit files or GitHub,
- services do not gain signing or transaction authority.

## 6. Verification

TDD is required for behavior changes.

Repository CI must prove:

- candidate selection is bounded, deterministic, point-in-time, and rejects invalid windows;
- runtime config rejects missing/invalid economic inputs and builds exact bidirectional probes;
- provider requirements fail closed;
- one daemon cycle invokes evidence collection for exactly the selected candidate set and aggregates reports without synthesizing success;
- service files contain no secrets or live/trading command paths;
- all existing Rust, Python, and repository-safety checks remain GREEN.

## Explicitly deferred from this slice

- Python multi-candidate paper campaign coordinator,
- E11/E12 campaign evaluation orchestration,
- dashboard/HTTP server,
- Telegram or other alert transport,
- backup/restore automation,
- live execution, signing, submission, or wallet secrets.

Those follow only after the real evidence stream can run continuously and restart safely.