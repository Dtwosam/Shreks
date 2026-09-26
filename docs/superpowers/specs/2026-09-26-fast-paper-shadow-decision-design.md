# Fast Lane Learned PAPER Shadow Decision — Design

**Date:** 2026-09-26  
**Base main SHA:** `002a4a4f255736cacf54d6df72c185c1291a3128`  
**Migration plan:** `docs/superpowers/plans/2026-09-26-fast-lane-learned-paper-runtime-migration.md`

## Goal

Implement the first learned-shadow runtime boundary after the sealed production
feature feed.

This slice evaluates one point-in-time Fast Lane feature row with the exact
approved champion and exact release-bound Rust campaign decision binary, then
records canonical shadow decision evidence.

It must not mutate the authoritative PAPER ledger, create an isolated shadow
ledger, change systemd service topology, or grant LIVE authority.

## Inputs

The shadow decision function consumes:

- one exact `FastPaperRuntimeManifest`;
- one exact `FastTrainingFeatureRecord`;
- an explicit `FastCampaignDecisionPosition`;
- point-in-time route/quote evidence;
- explicit maximum exposure and force-sell constraints;
- an evaluation timestamp.

The route/quote evidence is represented with a runtime-local read-only model:

`FastPaperShadowQuoteEvidence`

Fields bind:

- provider;
- mint and quote mint;
- quote observation timestamp;
- route state: `EXECUTABLE` or `UNAVAILABLE`;
- reference price;
- execution price;
- quoted/available base quantity.

Reduction evidence binds one target exposure fraction to one exact quote.

## Point-in-time validation

All route evidence must:

- match the feature row market;
- be observed no earlier than the decision timestamp;
- be observed no later than the supplied evaluation timestamp;
- use the exact decision executable reference price when executable;
- use only `EXECUTABLE` or `UNAVAILABLE` states.

No future-path labels, counterfactuals, or training targets may be imported.

## Constraint construction

The shadow adapter constructs `FastCampaignActionConstraints` rather than
accepting prebuilt constraints.

Rules:

- BUY is economically allowed only when both ENTRY and EXIT routes are
  currently executable and max exposure is positive;
- current/future exit cost uses the observed executable EXIT quote;
- SELL is executable only when the EXIT route is executable;
- reduction candidates are available only when an exact executable reduction
  quote exists for that target;
- unavailable quotes contribute no synthetic execution-cost estimate;
- `force_sell` remains explicit and fails closed if SELL is unavailable.

Execution-cost basis points are derived directly from point-in-time executable
prices:

- BUY: `max(0, execution/reference - 1) * 10_000`;
- SELL/reduction: `max(0, 1 - execution/reference) * 10_000`.

The current BUY cost is recorded as evidence but is not injected into the Rust
constraint schema because the active learned forecast already uses the sealed
entry-cost-adjusted-return target.

## Champion chronology

Before inference, the adapter reopens the exact manifest-bound champion and
requires:

- feature schema equality;
- every active target/horizon member required by the Rust action engine;
- champion selection time no later than the feature decision;
- every active model's maximum training decision time strictly earlier than
  the feature decision.

This prevents a champion trained on future observations from acting on an older
row.

## Decision execution

The adapter:

1. verifies all runtime manifest bindings;
2. builds exactly one campaign decision request from the canonical feature row;
3. invokes the existing release-local `shreks-fast-campaign-decision` through
   the existing offline runner with an explicit 30-second timeout;
4. re-verifies manifest bindings after the subprocess returns;
5. requires exact champion version/fingerprint alignment;
6. requires exact request/result identity and policy version;
7. records decision latency from a monotonic clock.

The adapter does not invoke scoring, legacy `decide_entry`, risk execution,
PAPER buy/sell execution, signing, submission, or provider/network clients.

## Evidence artifact

Schema:

`shreks.fast_paper_shadow_decision` v1.

The artifact binds:

- release SHA and runtime manifest fingerprint;
- champion version/fingerprint;
- action-policy version;
- source event identity/sequence/time/market;
- evaluation time;
- decision latency;
- position;
- derived constraints;
- route evidence and reduction quotes;
- exact Rust decision result;
- Rust result batch fingerprint;
- canonical artifact fingerprint.

Writes are:

- canonical JSON;
- one trailing newline;
- owner-only mode `0600`;
- non-overwriting.

The reader strictly authenticates the artifact fingerprint and all nested
model contracts.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
FUTURE_LABEL_ACCESS=FORBIDDEN
COUNTERFACTUAL_ACCESS=FORBIDDEN
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
SHADOW_LEDGER_EXECUTION=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
FAST_LANE_PAPER_EXECUTION=NOT_GRANTED
LIVE=DISABLED
```

## Following slice

After this decision-only evidence path is exact and merged, the next PR3 slice
may add durable/continuous shadow orchestration and, separately, an isolated
shadow ledger. It must still not mutate the authoritative PAPER ledger.
