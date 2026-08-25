# Phase E14 Safety Evidence Bridge Design

**Status:** Approved by standing project instruction for autonomous execution  
**Date:** 2026-08-25  
**Base:** sealed E13 `892ace744535e81b8bbea543a1d47ef46a2173c7`

## 1. Purpose

E13 proved a read-only, no-look-ahead bridge from the Rust observer SQLite market history into B2 market feature points. The next blocker to a real observer-history -> paper-proof campaign is B1 safety: the Python safety engine requires point-in-time authority, liquidity, holder concentration, exit-route, freshness, and execution-hazard facts before strategy scoring, and it deliberately returns `INCOMPLETE` when required evidence is unknown.

E14 closes that evidence gap without changing B1 rules and without granting execution authority.

The slice has three responsibilities:

1. capture normalized holder-distribution evidence from Helius;
2. persist successful read-only Jupiter exit-quote evidence with exact probe provenance;
3. assemble those facts, existing persisted mint-state history, and E13 market evidence into deterministic B1 `SafetyInputs` in Python.

E14 does not enable Phase F.

## 2. Existing Evidence Reused

E14 must reuse, not duplicate, sealed primitives that already exist:

- `token_mint_states` already persists Helius mint/freeze authority state and observation time;
- E13 `ObserverMarketStore` already provides one deterministic current market path and liquidity;
- `QuoteProvider`, `QuoteRequest`, and `QuoteSnapshot` already provide a read-only Jupiter route/build boundary including route availability and price impact;
- B1 `SafetyInputs`, `SafetyPolicy`, `SafetyAssessment`, and `assess_safety` remain unchanged.

The default Phase-A `build_free_observer` remains unchanged and continues to exclude Jupiter. E14 adds explicit safety-evidence collection surfaces; it does not silently alter the old unattended observer provider plan.

## 3. Safety Coverage Matrix

| B1 input | E14 source | Replay rule |
| --- | --- | --- |
| `mint_authority_active` | latest persisted `token_mint_states` row at/before `as_of` | authority string present => `True`, null => `False`; no row => `None` |
| `freeze_authority_active` | same mint-state row | authority string present => `True`, null => `False`; no row => `None` |
| `liquidity_usd` | E13 selected current market snapshot | preserve exact observed value |
| `top_holder_concentration_pct` | new complete Helius holder-distribution snapshot | largest aggregated owner balance / total observed token-account balance * 100; incomplete scan => `None` |
| `creator_concentration_pct` | unavailable in current normalized evidence | `None`; remains a soft unknown, never invented |
| `exit_quote_available` | new persisted successful Jupiter probe | exact `route_available`; no matching quote => `None` |
| `exit_price_impact_pct` | same matching quote | parsed finite percentage when supplied; missing => `None` |
| `execution_trap_detected` | no positive detector exists in current system | `False` means no detector fired; route failure is represented separately and no claim of trap absence is promoted to a critical fact |
| `critical_data_observed_at_unix_ms` | conservative oldest timestamp among the evidence actually used | never later than `as_of` |
| `critical_data_contradictory` | identity/provenance disagreement | exact-reader filters prevent mixing; malformed contradictory evidence fails closed |
| `global_risk_halt` | explicit caller state | required argument; never defaulted by storage replay |

## 4. Holder Distribution Semantics

`top_holder_concentration_pct` must describe wallet-owner concentration, not merely the largest SPL token account.

E14 therefore adds a provider-neutral `TokenHolderDistribution` domain value and a separate `DistributionDataProvider` trait.

The Helius implementation uses `getTokenAccounts` filtered by mint and paginates through token-account rows using the API's page-number pagination. Each row supplies an owner and raw token amount. E14 aggregates raw amounts by owner before choosing the largest owner.

The request is bounded by an explicit caller/provider policy:

- page size;
- maximum pages.

A page shorter than the requested page size, or an empty page, proves completion. If the maximum-page budget is reached after a full page, completion is not proven: the observation is marked incomplete and no hard-safety `top_holder_concentration_pct` is exposed. A partial scan may be retained for audit, but it must never be treated as complete concentration evidence.

The provider snapshot records at least:

- provider;
- mint;
- local observation timestamp;
- token accounts scanned;
- unique owners scanned;
- pages scanned;
- scan completeness;
- total raw token-account balance scanned;
- largest owner address when known;
- largest owner raw balance when known;
- concentration percentage only when the scan is complete and total raw balance is positive.

The complete-scan denominator is the sum of raw balances across all returned token accounts. This avoids adding a second hidden supply query to the distribution API and keeps the concentration calculation self-contained in one complete point-in-time scan. Zero-balance accounts do not affect the denominator.

Raw integer token units are kept as unsigned integers/decimal text across SQLite boundaries; percentages are derived only after checked arithmetic.

## 5. Exit Quote Evidence Semantics

E14 does not choose a trade size. Quote sizing before strategy/risk sizing would otherwise create a hidden economic assumption.

A caller supplies the exact `QuoteRequest` plus a non-empty `probe_policy_version`. The collector verifies that:

- input mint is the candidate mint;
- output mint, raw input amount, taker, and slippage are explicit;
- returned `QuoteSnapshot` matches the request through the sealed provider validation;
- only successful normalized snapshots are persisted.

Provider transport/rate-limit/parse failures do not become `exit_quote_available=False`; absence of a valid matching row remains `None`/unknown in B1. A successful normalized quote with `route_available=False` is explicit unavailable evidence and may produce B1 hard reject.

Persisted quote evidence contains exact request/response attribution and the probe policy version so replay cannot accidentally compare a quote produced under a different probe definition.

## 6. Storage

Add one append-only migration after schema version 7.

### `token_holder_distributions`

Stores one normalized holder scan per candidate/provider/observation identity. Required columns include candidate id, provider, mint, observation time, account/owner/page counts, completeness, total raw balance text, largest-owner provenance, largest-owner raw balance text, and complete concentration percentage when available.

### `exit_quote_snapshots`

Stores one successful normalized read-only quote per candidate/probe/request/time identity. Required columns include candidate id, provider, probe policy version, input/output mints, raw amounts as decimal text, slippage, route availability, price impact text or normalized percentage, route labels as canonical JSON text, and quote time.

Both tables are foreign-keyed to `token_candidates`, indexed by candidate/time, and use semantic uniqueness so retries are idempotent.

No trade intent, signature, signed transaction, serialized executable transaction, private key, or secret is persisted.

## 7. Rust Collection Boundary

E14 adds explicit collection APIs but does not change `free_observe_provider_plan` or `build_free_observer`.

A safety-evidence collector accepts:

- `ShreksDb`;
- one or more `DistributionDataProvider`s;
- one or more `QuoteProvider`s;
- exact candidate identity;
- exact holder-scan request policy;
- exact quote request + probe policy version.

Provider failures are returned/recorded as evidence-collection failures; they do not manufacture successful safety facts.

The collector has no dependency on signing, transaction submission, registry promotion, or live execution.

## 8. Python Read/Assembly Boundary

Add an isolated `shreks_brain.observer_safety` package.

Its read-only store opens the same SQLite database using URI `mode=ro`, validates required existing/new columns while allowing additive future columns, and exposes a small API to build point-in-time `SafetyInputs` from:

- an exact E13 `ObservedMarketWindow`;
- latest compatible mint state at/before `as_of`;
- latest complete holder distribution at/before `as_of`;
- latest quote matching candidate + exact probe policy/request identity at/before `as_of`;
- explicit caller `global_risk_halt`.

It then delegates evaluation to sealed B1 `assess_safety`; it does not duplicate safety thresholds or finding logic.

If required evidence is absent, B1 receives `None` and produces `INCOMPLETE` according to its existing policy. No optimistic defaults are allowed.

## 9. Point-in-Time and Contradiction Rules

- Never select a row with observation/quote time after `as_of_unix_ms`.
- Mint, distribution, quote, and market identities must all match the requested candidate mint.
- Quote replay must match probe policy version and exact request identity.
- Holder concentration is usable only for a complete scan.
- The critical timestamp is the oldest timestamp among the concrete critical evidence used in the assessment, making freshness conservative.
- Invalid percentages, raw amounts, timestamps, or identity mismatches fail closed at the E14 boundary.
- Provider failures do not become positive/negative safety facts unless the normalized provider result explicitly says so.

## 10. Authority Firewall

E14 must not:

- modify B1 safety thresholds or precedence;
- modify B2 feature arithmetic;
- modify E5-E13 sealed evaluation/promotion/proof behavior;
- create a paper fill;
- create a live trade intent;
- sign or submit a transaction;
- mutate champion/challenger registry state;
- auto-promote any model;
- enable runtime `Live`;
- add Jupiter to the default Phase-A observer plan.

Jupiter remains read-only through `QuoteProvider`.

## 11. TDD Plan Shape

Implementation will be split into small independently verified RED/GREEN tasks:

1. provider-neutral distribution models + Helius page-number pagination/aggregation;
2. storage migration + idempotent holder/quote persistence;
3. explicit Rust safety-evidence collector with no default-observer wiring;
4. Python read-only safety evidence models/store/assembler and exact B1 evaluation;
5. public API/authority firewall, cumulative scope audit, verification record, immutable seal.

Each RED anchor must fail for the intended missing behavior while unaffected CI lanes remain green. Every GREEN head must pass full repository CI before advancing.
