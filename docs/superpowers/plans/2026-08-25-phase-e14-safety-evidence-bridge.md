# Phase E14 Safety Evidence Bridge Verification Record

**Status:** behavior complete and frozen; this document is the verification seal record.

**Base:** sealed E13 `892ace744535e81b8bbea543a1d47ef46a2173c7`

**E14 behavior head:** `ac874d36b72034e4e4d062394459ca1f5a687b59`

**Design:** `docs/superpowers/specs/2026-08-25-phase-e14-safety-evidence-bridge-design.md`

## Purpose

E14 closes a proof-quality safety-data gap without widening trading authority. It adds complete holder-distribution evidence, normalized read-only exit-quote evidence, restart-safe persistence, an explicit opt-in Rust safety-evidence collector, and a Python point-in-time assembler that reconstructs sealed B1 `SafetyInputs` from persisted observer evidence.

E14 does not change the default Phase-A observer, does not change sealed B1 safety thresholds or precedence, does not change B2 feature arithmetic, and does not grant execution, signing, submission, registry mutation, promotion, live-mode, or Phase-F authority.

## Verified Behavioral Contract

### Holder distribution

- Provider-neutral bounded `TokenDistributionRequest` and normalized `TokenHolderDistribution` contracts exist.
- Helius scans token accounts using bounded page-number pagination and aggregates raw `u64` balances by owner.
- Only a proven-complete scan may expose `top_holder_concentration_pct`.
- A max-page-budget truncation remains incomplete and therefore exposes concentration as unknown.
- Provider/mint response attribution is validated rather than trusted implicitly.

### Persistence

- Migration `0008_safety_evidence.sql` adds normalized holder-distribution and exit-quote evidence tables.
- Full-width Solana/Jupiter raw integer values are preserved as canonical decimal text where SQLite signed integers are insufficient.
- Exact semantic replays are idempotent.
- Same-identity contradictory evidence fails closed instead of rewriting history.
- Holder evidence must match the candidate mint.
- Exit-quote persistence preserves the exact probe identity, including probe policy version, input/output mint, taker, raw input amount, slippage, route availability, price-impact text, route labels, and quote timestamp.
- No signed transaction or provider credential is persisted by this bridge.

### Explicit collector

- `SafetyEvidenceCollector` is opt-in and constructed explicitly from `ShreksDb`, distribution providers, and quote providers.
- Provider transport failures produce failure counts and no synthesized safety evidence.
- Misattributed successful provider results are rejected and not persisted.
- A successful normalized quote with `route_available=false` is persisted as explicit unavailable evidence.
- Duplicate collection is idempotent.
- Normal `Observer::run_cycle` is unchanged.
- `free_observe_provider_plan` continues to exclude Jupiter.
- `build_free_observer` has no safety collector by default.

### Python point-in-time assembly

- `ObserverSafetyEvidenceStore` opens SQLite read-only using URI `mode=ro`; a missing database is not created.
- Missing required tables/columns fail closed; additive future columns are allowed.
- Readers never select evidence timestamped after caller `as_of`.
- Candidate/mint, Helius holder/mint, and exact Jupiter probe attribution are enforced.
- Incomplete holder rows expose concentration as `None` even if a raw database value exists.
- Missing exact quote evidence remains unknown; explicit route-unavailable evidence becomes `exit_quote_available=False`.
- Authority booleans are derived only from presence/absence of authority addresses in an actual persisted mint-state row.
- Quote price impact is parsed strictly as finite percentage points within `[0, 100]`; malformed/non-finite/out-of-range text fails closed.
- `critical_data_observed_at_unix_ms` is the oldest timestamp among evidence actually consumed, including the selected market snapshot.
- Creator concentration remains `None`; execution-trap evidence is not guessed.
- `assess_observer_safety` delegates to sealed B1 `assess_safety`; E14 duplicates no B1 threshold logic.

## Exact Python Public API

`shreks_brain.observer_safety.__all__` is exactly:

1. `ObserverSafetyProbeIdentity`
2. `ObserverMintSafetyEvidence`
3. `ObserverHolderSafetyEvidence`
4. `ObserverExitQuoteSafetyEvidence`
5. `ObserverSafetyReadError`
6. `ObserverSafetyEvidenceStore`
7. `ObserverSafetyAssemblyError`
8. `build_safety_inputs`
9. `assess_observer_safety`

`ObserverSafetyEvidenceStore` exposes exactly these public callable methods:

- `latest_mint_state`
- `latest_holder_distribution`
- `latest_exit_quote`

Fresh-process/source import firewall tests reject observer-safety dependencies on paper execution, paper loop/evaluation, registry, promotion, shadow, execution, or live packages. Public callable names are also audited against write/save/insert/update/delete/execute/trade/promote/live/sign/submit authority verbs.

## RED / GREEN Evidence

| Task | RED anchor | RED CI | Verified RED boundary | GREEN anchor | GREEN CI | Python evidence | Other lanes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 — holder distribution + Helius | `f9ffbb7d81face57b4d90a82c6cbe6029c9a2b56` | `32855653678` | Rust failed only on absent distribution core/provider/Helius API surface; Python and safety GREEN; workspace metadata GREEN | `1ef86746a382f7f9c7f1761bc90c47b6bb3d0200` | `32856185391` | `2137 passed in 7.94s` | Rust/workspace GREEN; repository safety GREEN |
| 2A — migration/schema | `dc535277047598900378313ccdba93b11e5cff5f` | `32856568282` | New migration/schema requirements were absent | `2d3ca00bed93caf39471a9f5bf8d19fdeeccd2d1` | `32858111912` | `2137 passed in 8.33s` | Rust/workspace GREEN; repository safety GREEN |
| 2B — persistence | `32266a14dee578127ed29f2d50b64ec7c8691826` | `32858757769` | Rust failed only because holder/quote persistence methods were absent; Python and safety GREEN | `f897298b086e209b1b2718bd1a98f2c1fdaedcb7` | `32859529134` | `2137 passed in 8.16s` | Rust/workspace GREEN; repository safety GREEN |
| 3 — explicit collector | `cc790e5f76430df89ea48a600aefb0504cb156d2` | `32859823590` | Python/safety GREEN; Rust failed only on absent collector module/types/exports | `6d7901fe096d8438fb233022d28b2403f6bc9aa2` | `32860519712` | `2137 passed in 7.67s` | Rust/workspace GREEN; repository safety GREEN |
| 4A — Python models/store | `0fa9e41174e773896ef7e26d983a23dbba913d14` | `32861055549` | Rust/safety GREEN; Python failed only because `shreks_brain.observer_safety` did not yet exist | `c5489776e4940b9f7b7013c4b5b311e581034d8e` | `32861846721` | `2160 passed in 7.51s` | Rust/workspace GREEN; repository safety GREEN |
| 4B — B1 assembler | `c3648279cddd2b77bf933cce1a14b6850ecb78eb` | `32862243493` | Safety GREEN; Python failed only because `observer_safety.assembler` was absent | `64a9cb63ff5f72d5192096ff4c90ffba5af997a6` | `32862382264` | `2177 passed in 7.04s` | Rust/workspace GREEN; repository safety GREEN |
| 5 — public API / authority | `adcd37fb1320b1d2b31e2b8f5d77f46b9d16f336` | `32862553659` | `4 failed, 2178 passed`; all four failures were the missing concrete export surface | `ac874d36b72034e4e4d062394459ca1f5a687b59` | `32862677598` | `2182 passed in 8.48s` | Rust/workspace GREEN; repository safety GREEN |

## Mechanical Collector Export Audit

The collector implementation-to-export boundary was checked separately:

- base `91bb5e02a716639d7dbf49059d6e8375e019dc7c`
- head `6d7901fe096d8438fb233022d28b2403f6bc9aa2`
- ahead exactly one commit
- changed exactly one file: `crates/shreks-observer/src/lib.rs`
- `4` additions / `0` deletions

Therefore exporting the collector did not rewrite existing observer behavior.

## E13 -> E14 Scope Audit

Compare base `892ace744535e81b8bbea543a1d47ef46a2173c7` to behavior head `ac874d36b72034e4e4d062394459ca1f5a687b59`:

- ahead `27`, behind `0`
- changed scope is limited to:
  - E14 design/verification-plan documentation;
  - provider-neutral distribution contracts in `shreks-core`;
  - distribution provider boundary and Helius distribution adapter/tests;
  - safety-evidence SQLite migration, persistence, and storage tests;
  - isolated observer `safety_evidence` collector/tests plus its export hook;
  - isolated Python `observer_safety` models/store/assembler/API and tests;
  - existing storage schema-version expectation tests required by migration 8.

Specifically absent from the E13 -> E14 diff:

- B1 safety evaluator or policy logic changes;
- B2 feature arithmetic changes;
- paper executor or live executor changes;
- registry or promotion changes;
- risk-authority changes;
- signing or submission changes.

## Authority and Profitability Boundary

E14 is an evidence-quality bridge. It makes holder concentration, authority state, liquidity freshness, and executable exit-route evidence more trustworthy and restart-replayable. It does **not** prove that a strategy is profitable, does **not** establish positive expectancy after costs, does **not** satisfy the independent-paper-sample or drawdown requirements, and does **not** satisfy the full Phase-F live gate by itself.

No E14 component can sign or submit a transaction, mutate champion/challenger promotion state, enable live mode, or bypass the sealed B1 safety evaluator. Provider failures and missing/incomplete evidence remain unknown and therefore fail closed under B1 when the relevant fact is required.

**Phase F/live trading remains disabled.**

## Behavior Freeze and Seal Procedure

The immutable E14 behavior head is `ac874d36b72034e4e4d062394459ca1f5a687b59`, verified by exact-head CI `32862677598` with Python `2182 passed in 8.48s`, Rust/workspace GREEN, and repository safety GREEN.

This verification record is the only file permitted to change after that behavior head. The resulting documentation commit must be verified to be exactly one commit / one file ahead of the behavior head, followed by a fresh exact-seal full CI run. The stacked PR remains draft/unmerged.
