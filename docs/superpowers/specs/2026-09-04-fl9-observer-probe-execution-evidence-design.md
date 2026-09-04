# FL9 Observer-Probe Execution Evidence — Design

**Date:** 2026-09-04

## Status

Implementation slice after champion-derived FL3 execution evidence merge
`7fee5ef7f7ec00ab1d2b12cefa353a9017b70805` (#189).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Remove the final caller-picked trade-quantity fields from the real deterministic comparison path.

The sealed point-in-time hydrator already reads exact observer ENTRY and EXIT Jupiter quote evidence. This slice makes those same persisted probes authoritative for:

- PAPER directional quote reconstruction;
- intended base quantity;
- proven exit capacity;
- directional quote provenance;
- ENTRY price-impact attribution;
- ENTRY impact notional.

No separate sizing calculator is allowed to reinterpret the same row.

## Canonical probe object

`load_fast_observer_directional_probe(...)` returns one frozen
`FastObserverDirectionalProbeEvidence` for one FL8.1 decision row.

It reads only through existing `ObserverCampaignStore`:

1. latest Helius token decimals for the exact observer candidate + mint as-of the explicit evaluation clock;
2. exact persisted ENTRY quote identity as-of that clock;
3. exact persisted EXIT quote identity as-of that clock.

The loader requires:

`decision_observed_at <= quote_observed_at <= evaluated_at`

for both directions.

Missing decimals or either directional quote row fails closed.

## Intended base quantity

For an executable ENTRY route:

`intended_base_quantity = ENTRY output_amount / 10^token_decimals`.

This is the exact token quantity returned by the persisted quote probe.

If ENTRY is unavailable, intended quantity is `None` and no champion-derived execution evidence may be created.

## Proven exit capacity

For an executable EXIT route:

`exit_capacity_base = EXIT input_amount / 10^token_decimals`.

This is intentionally conservative.

The stored EXIT probe proves that the route was executable for that exact token input amount. It does **not** claim that this is the route's maximum possible capacity.

If the EXIT probe input is smaller than intended ENTRY quantity, the smaller positive value is preserved. Sealed FL6 then records `InsufficientExitCapacity` SKIP.

If EXIT is unavailable, capacity is `None` and no entry execution object is created.

## Directional quote reconstruction

ENTRY uses:

- quote input raw amount;
- token output raw amount.

EXIT uses:

- token input raw amount;
- quote output raw amount.

The resulting `FastCampaignPaperQuoteEvidence` values are also what the point-in-time hydrator consumes.

The hydrator no longer owns duplicate raw-amount conversion logic.

## Champion execution adapter

`build_fast_observer_champion_entry_execution(...)` accepts:

- canonical observer probe;
- authenticated champion path;
- exact FL8.1 record;
- horizon;
- explicit FL3 cost model;
- required edge;
- risk margin;
- execution-policy source version.

It does **not** accept base quantity or exit capacity.

When both directional routes are executable, it delegates to the sealed champion execution adapter with:

- base quantity from ENTRY probe;
- exit capacity from EXIT probe;
- exit-capacity source version equal to the exact EXIT quote source identity.

When either route is unavailable, it returns `None` without launching champion inference.

## Hydrator alignment

If a caller supplies shared FL6 execution evidence to the point-in-time hydrator, the hydrator now requires:

- execution base quantity == canonical ENTRY probe quantity;
- execution exit capacity == canonical EXIT probe capacity;
- exit-capacity source version == canonical EXIT quote source version.

This closes the remaining path where canonical quotes were loaded but a separate execution object could carry friendlier size/capacity values.

All four FL6 entry families must still share the exact same execution object.

## Provenance

Directional source identities are canonical:

- `observer:<provider>:<probe_policy_version>:entry`;
- `observer:<provider>:<probe_policy_version>:exit`.

The EXIT source identity is the only accepted exit-capacity provenance for hydrated execution evidence.

## Risk attribution

The canonical probe also derives:

- ENTRY input notional USD from raw quote input + explicit quote-asset decimals/USD rate;
- ENTRY price-impact percent from the persisted quote.

The hydrator compares its shared risk environment against those exact canonical values.

## Authority boundary

No:

- database writes;
- direct sqlite access in the probe adapter;
- provider/network calls;
- hidden clock;
- future labels;
- direct PAPER fill execution;
- superiority evaluation;
- promotion;
- signing/submission;
- LIVE authority.

## TDD

Intentional RED:

`aa9ded8c9a52ebae4908041bb44c6a853498bd61`.

Coverage includes:

1. exact ENTRY quantity reconstruction;
2. exact EXIT capacity reconstruction;
3. exact directional PAPER prices;
4. exact directional source identities;
5. champion builder receives no caller-picked size/capacity;
6. unavailable ENTRY/EXIT returns no execution evidence;
7. positive undersized EXIT capacity remains explicit;
8. hydrator rejects size drift;
9. hydrator rejects capacity drift;
10. hydrator rejects noncanonical capacity provenance;
11. hydrator reuses canonical probe conversion;
12. source authority firewall.

## Following slice

Build a reproducible campaign-input assembler that combines:

- exact FL8.1 population;
- canonical observer directional probes;
- authenticated post-training/post-selection FL8 champion;
- explicit execution-cost/edge/risk-margin policy;
- explicit point-in-time regime/risk/wallet/lifecycle context;

into the existing hydration inputs and immutable v2 comparison bundle.

No fixture result may be described as economic proof.
