# Zero-Cost Direct Solana Capture Design

## Status

FL1/FL1.5 production-cost repair following the physical 2026-08-30 sanity run of sealed release `2d47bfe3c59ae4c7b673366a4eaff8d02919afcd`.

**LIVE TRADING: DISABLED.** Production observer and paper-evidence remain stopped until this repair and the ready-row canonicalization follow-up are sealed, deployed, and physically accepted.

## Production evidence

The three-minute physical sanity interval on the sealed bounded-PumpSwap release proved:

- exact release/process identity passed;
- Helius realtime authentication passed;
- `pump_raw_events=7214`;
- `pumpswap_raw_events=963`;
- all raw provenance was `helius`;
- sequence-integrity violations were zero;
- canonical-conflict violations were zero;
- canonical events were zero;
- observer restart count increased from 0 to 1;
- the interval consumed roughly 5,000 Helius credits according to the operator's provider-side counter.

The PumpSwap global firehose was therefore successfully removed, but the remaining global Pump-program subscription is still economically incompatible with the project's hard zero-paid-provider constraint. Helius currently meters standard WebSocket traffic by bytes; receiving every Pump trade on Helius is not sustainable within the free allowance.

## Governing objective

Provider-cost optimization must not reduce Shreks' ability to make money.

That means the repair may change **where** Shreks obtains direct Solana data, but it must not intentionally reduce the Pump/PumpSwap economic information captured for FL1. The build-order requirements remain authoritative: creation, pre-graduation buys/sells, reserve changes, migration, PumpSwap trades, wallet/signature/slot/timestamp attribution, deterministic identity, and replayability remain required.

## Architecture

### 1. Free direct-chain realtime becomes the broad coverage lane

Use Solana's public mainnet JSON-RPC/WebSocket endpoint for the broad FL1 observation lane:

- HTTPS: `https://api.mainnet.solana.com`
- WSS: `wss://api.mainnet.solana.com`

The public service is rate-limited and has no production SLA, so it is an observation source, not an execution dependency. Failure remains fail-closed and visible. Shreks must never interpret public-endpoint availability as trading authority.

The existing standard-Solana `logsSubscribe` protocol is preserved. The public realtime stream subscribes to:

1. the Pump bonding-curve program globally, preserving all pre-graduation event coverage; and
2. the already-bounded verified PumpSwap pool set, preserving post-graduation scope.

No global PumpSwap AMM subscription returns.

### 2. Truthful provenance

Add `ProviderId::SolanaPublic` serialized as `solana_public`.

Raw Pump/PumpSwap rows and canonical FastEvents received from the public endpoint retain `solana_public` provenance. Existing Helius/Chainstack/Alchemy provenance semantics remain unchanged. No source may be relabeled to preserve legacy expectations.

No database migration is required because provider columns are textual and already accept nonblank values; decoding/validation code must explicitly recognize the new provider id.

### 3. Helius is removed from broad observer streaming

The production observer must never construct a global Pump-program Helius subscription.

Helius credentials may remain configured for other isolated services, but `shreks-observe` broad realtime must not consume Helius WSS credits. Chainstack and Alchemy also remain excluded from this broad production lane so provider failure cannot silently rotate into a billable/unbounded source.

A later optional acceleration layer may subscribe Helius only to a bounded set of verified active mints/pools after measured need. That is a separate change and may not reintroduce a global Pump subscription.

### 4. Free read-only verification

Use the Solana public HTTPS RPC as the observer's standard read-only provider for:

- confirmed `getTransaction` Pump create/migration verification;
- SPL mint `getAccountInfo`/`jsonParsed` state needed for decimals and normalization.

The existing request pacing remains conservative. Public RPC 403/429/unavailability is provider failure and leaves evidence pending/unknown; it never becomes a safe fact.

This removes observer Helius HTTP/RPC consumption from the normal FL1 path. The paper-evidence daemon keeps its independent Helius/Jupiter configuration and remains stopped during FL1.5 cost acceptance.

### 5. Profitability/latency invariant

The repair must preserve the same direct Pump/PumpSwap log payloads and parsers. It does not replace event-level data with DEX Screener polling, candles, or aggregated snapshots.

Because public RPC may have different observation latency from Helius, FL1.5 must record source-to-canonical latency before advancing. If later strategy benchmarks show that public-source latency materially reduces expected net edge, add a separately bounded Helius active-mint accelerator rather than returning to global metered streaming.

### 6. Failure and supervision

Realtime-source exit is mandatory-lane failure. The runtime supervisor must observe the forwarder task directly and return the primary provider error rather than relying on downstream channel closure to reveal it indirectly.

Sibling task shutdown must not overwrite the first causal error with a secondary `target publisher stopped` message.

### 7. Runtime configuration

The existing explicit PumpSwap bounds remain required:

- `SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS`
- `SHREKS_PUMPSWAP_MAX_TRACKED_POOLS`

The observer Helius request-budget variable is no longer a startup requirement merely because `HELIUS_API_KEY` exists, because the zero-cost observer path does not construct a Helius provider. Paper-evidence retains its separate mandatory Helius budget.

No new paid-provider configuration is introduced.

## Non-goals

- no strategy, score, action, risk, sizing, signing, wallet, PAPER, SHADOW, LIVE, or FL2 authority changes;
- no provider plan upgrade;
- no paid PumpPortal trade subscription;
- no global Helius Pump or PumpSwap subscription;
- no database schema migration;
- no reinterpretation of historical provider provenance;
- no claim that public Solana RPC has an SLA.

## TDD requirements

Tests must prove at minimum:

1. `ProviderId::SolanaPublic` serializes as `solana_public` and stored Fast Lane rows round-trip it.
2. standard Solana mint-state parsing accepts `SolanaPublic` and preserves provenance.
3. `StandardSolanaRpcProvider::solana_public()` uses the official HTTPS endpoint and redacts it from Debug/errors.
4. bounded realtime config accepts `SolanaPublic`, uses the official WSS endpoint, and keeps the global Pump + bounded-pool plan with no global PumpSwap subscription.
5. production runtime constructs the broad realtime lane from SolanaPublic only even when Helius/Chainstack/Alchemy credentials are configured.
6. production lifecycle observer uses SolanaPublic for transaction/mint verification and does not construct `HeliusProvider` or Chainstack for the observer path.
7. Helius key presence alone no longer requires `SHREKS_OBSERVER_HELIUS_MAX_REQUESTS_PER_PROCESS` in observer runtime config.
8. realtime forwarder termination is supervised as a primary error.
9. source-inspection tests reject global Helius Pump streaming and reject any `PUMP_AMM_PROGRAM_ID` production subscription.
10. no trading/signing/LIVE authority appears in the diff.
11. repository safety, Rust, Python, and ARM64 release-build gates pass on the exact PR head.

## Physical acceptance after seal/deploy

Run a short sanity interval first, then representative FL1.5 only if sanity is stable.

Require:

- exact immutable release/process identity;
- observer restart count unchanged;
- `pump_raw_events > 0`;
- `pumpswap_raw_events > 0` when natural tracked-pool activity exists;
- provider counts show `solana_public` for broad FL1 rows;
- zero sequence-integrity violations;
- zero canonical-conflict violations;
- no Helius WSS usage increase attributable to `shreks-observe`;
- no Chainstack/Alchemy usage;
- provider/source latency retained as measured evidence;
- no persistent reconnect churn.

If the public endpoint cannot sustain the observed workload, FL1.5 remains HOLD and the next zero-cost fallback must be engineered explicitly. Do not silently rotate to a paid provider.

**LIVE TRADING remains disabled throughout.**
