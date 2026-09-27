# Fast PAPER Shadow BUY Authority Producer — Design

**Date:** 2026-09-27  
**Base main SHA:** `f768f029431f9a74f2dcc97d225af6eb9e2d2998`

## Purpose

Add the smallest reusable producer core that turns already point-in-time BUY
economics plus explicit market/risk context into the existing authenticated
initial BUY-authority source record.

This closes a key gap between learned BUY decisions and the already-sealed BUY
source publisher without inventing sizing, maximum entry prices, account state,
or market regime.

The producer does not persist the source record and does not execute PAPER.

## Inputs

The producer consumes exact current:

- Fast PAPER runtime manifest;
- isolated shadow ledger binding;
- execution policy;
- latest PAPER checkpoint;
- latest learned runtime state;
- sealed learned BUY decision evidence;
- matching `FastTrainingFeatureRecord`;
- explicit `FastOfflineEntryExecution`;
- explicit `FastDeterministicCampaignRiskEnvironment`;
- explicit exact `MarketRegime`;
- release-local `shreks-fast-entry-authority` binary path;
- source observation timestamp/version/fingerprint.

## Feature and decision binding

Before invoking FL3 derivation:

- the feature record fingerprint must equal
  `feature_logical_fingerprint_sha256((record,))` sealed in the decision;
- source-event identity must equal
  `<decision_signature>:<decision_ordinal>`;
- mint and quote mint must match the sealed decision entry quote;
- the decision must be BUY from FLAT posture;
- the risk environment trading capital must equal the isolated ledger's
  starting cash;
- external active-intent claims are forbidden;
- risk market evidence and the producer source observation must not be from the
  future;
- the producer source observation must be at/after the risk market observation.

## Entry authority

The only permitted maximum-entry derivation is the already-sealed FL3 adapter:

`derive_fast_deterministic_entry_authority_offline(...)`

using exactly the matching feature record and supplied
`FastOfflineEntryExecution`.

The producer must not duplicate FL3 execution-economics formulas.

If the sealed adapter returns `None` because the trade is not economically
buyable at the decision price/capacity, the producer returns `None`. It must
not manufacture a BUY authority.

## Risk context

The producer must build BUY risk context only through:

`build_fast_deterministic_campaign_risk_context(...)`

using the current isolated `PaperLedger`, the explicit risk environment, and
the sealed decision evaluation timestamp.

This recomputes open positions/risk, realized PnL, drawdown, and loss streak
from the isolated ledger while retaining only explicit external liquidity,
impact, freshness, health, kill-switch, and operator-halt facts.

The producer does not call the risk assessment engine; execution remains the
risk-authority boundary.

## Output

On an economically valid BUY, delegate final authentication to the existing:

`build_fast_paper_shadow_buy_authority_source_record(...)`

using:

- derived exact entry authority;
- derived exact risk context;
- explicit market regime;
- risk-day start from the explicit risk environment;
- explicit source observation/version/fingerprint.

Return the exact
`FastPaperShadowBuyAuthoritySourceRecord`.

## Authority boundary

```text
BUY_MAX_ENTRY_DERIVATION=SEALED_FL3_ONLY
BUY_LEDGER_RISK_ACCOUNTING=SEALED_LEDGER_HELPER_ONLY
BUY_EXTERNAL_RISK_FACTS=EXPLICIT_ONLY
MARKET_REGIME=EXPLICIT_ONLY
BUY_AUTHORITY_RECORD_BUILD=GRANTED
BUY_AUTHORITY_PERSISTENCE=NOT_GRANTED
EXECUTION_SOURCE_PUBLICATION=NOT_GRANTED
PAPER_EXECUTION=NOT_GRANTED
PROVIDER_NETWORK_ACCESS=NOT_GRANTED
OBSERVER_DATABASE_ACCESS=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
LIVE=DISABLED
```

The module must not import/invoke provider or observer database clients,
scoring/legacy decision authority, source writers, execution-source publishers,
PAPER execution, signing/submission, future labels, counterfactuals, or LIVE.

## RED acceptance

Intentional RED tests require:

- one public producer API;
- exact feature/decision identity binding;
- exact FL3 adapter delegation;
- truthful `None` when FL3 refuses BUY authority;
- isolated-ledger risk-context construction through the existing builder;
- explicit regime/source provenance forwarding;
- stale/mismatched external risk facts fail closed;
- no persistence, provider/network, scoring, execution, or LIVE authority.

Current main is expected to fail during Python collection because the producer
module/public API does not exist.

## Following slice

After this producer core is sealed, add the point-in-time runtime adapter that
assembles its explicit `FastOfflineEntryExecution`, regime, and external risk
environment from already-persisted production evidence/control state and writes
the resulting authenticated BUY-authority source record. That adapter remains
separate so provider/observer evidence authority can be reviewed independently.
