# Fast PAPER Shadow Execution Input Authority — Design

**Date:** 2026-09-26  
**Base main SHA:** `8bb9ff3aca89d007d40a4b9d12cba33e3b3bf839`

## Purpose

Add the smallest authenticated authority boundary needed before the learned
Fast PAPER shadow runtime may mutate its isolated ledger.

The learned continuous-action result intentionally carries normalized
policy/risk exposure, not token quantity. Existing FL9 design explicitly
reserves real sizing/account mapping for FL10. Therefore this slice must not
derive BUY base quantity, notional, or a maximum acceptable entry price from a
selected exposure fraction.

Instead, the runtime accepts those values only as explicit existing Fast PAPER
execution authority.

## Static execution policy artifact

Add one canonical private policy artifact:

`shreks.fast_paper_shadow_execution_policy` version `1`.

It binds:

- exact Fast PAPER runtime manifest fingerprint;
- exact `RiskPolicy`;
- exact `PaperFillPolicy`;
- exact `FastPaperPositionActionPolicy`;
- deterministic policy fingerprint.

Validation requires:

- risk-policy version == runtime-manifest risk-policy version;
- fill-policy version == runtime-manifest fill-policy version;
- position-action-policy version == runtime-manifest position-action-policy
  version;
- risk required decision-policy version == runtime assessment version;
- risk required feature/state version == runtime state version.

Unknown/missing fields, raw non-finite floats, fingerprint mismatch, symlinks,
or non-canonical payloads fail closed. The file is write-once and mode `0600`.

The artifact contains no `ScorePolicy`, legacy `DecisionPolicy`, scoring
threshold, setup approval, price, position, or runtime action.

## Per-decision execution input

One `FastPaperShadowExecutionInput` binds an already-sealed
`FastPaperShadowDecisionEvidence` to only the extra point-in-time authority
required by the existing Fast PAPER executor:

- optional exact `FastCampaignPaperEntryAuthority`;
- optional exact `RiskContext`;
- optional exact `MarketRegime`;
- optional exact quote-asset/USD evidence.

Quote/USD evidence identifies:

- quote mint;
- observed-at timestamp;
- positive finite quote-to-USD rate;
- non-empty source version;
- source fingerprint.

Future USD evidence is rejected.

### Action rules

**SKIP**

- requires FLAT learned posture;
- carries no entry/risk/regime/USD execution authority;
- materializes no PAPER quote.

**BUY**

- requires FLAT learned posture;
- requires exact entry authority;
- requires exact RiskContext at the execution-evaluation timestamp;
- requires exact MarketRegime;
- requires quote/USD evidence;
- requires executable ENTRY shadow quote;
- entry-authority pair and decision executable price must match the sealed
  shadow evidence;
- no exposure-to-size conversion is performed.

**HOLD**

- requires OPEN learned posture;
- forbids BUY entry/risk/regime authority;
- requires quote/USD evidence;
- materializes the generic EXIT quote so existing Fast PAPER position marking
  semantics remain authoritative.

**REDUCE**

- requires OPEN learned posture;
- forbids BUY entry/risk/regime authority;
- requires quote/USD evidence;
- materializes the exact reduction quote whose target exposure equals the
  learned selected target. The generic full EXIT quote must not be substituted.

**SELL**

- requires OPEN learned posture;
- forbids BUY entry/risk/regime authority;
- requires quote/USD evidence;
- materializes the generic EXIT quote.

Unavailable persisted routes remain unavailable PAPER quote evidence; this
adapter does not synthesize a fill.

## Adapter output

The adapter returns the existing sealed
`FastCampaignPaperDecisionEvidence` type consumed by Fast PAPER campaign
execution.

It does not call execution itself.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
SHADOW_EXECUTION_POLICY=AUTHENTICATED_INPUT_ONLY
SHADOW_BUY_SIZING=EXPLICIT_EXISTING_AUTHORITY_ONLY
EXPOSURE_TO_TOKEN_QUANTITY_INFERENCE=FORBIDDEN
SHADOW_LEDGER_MUTATION=NOT_GRANTED
SHADOW_SERVICE_INTEGRATION=DEFERRED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

The module must not import or invoke:

- scoring or legacy decision authority;
- BUY/position execution functions;
- provider/network clients;
- SQLite;
- signing/submission;
- future labels/counterfactuals;
- LIVE mode.

## Following slice

A separately reviewed incremental isolated executor may consume this contract,
the durable shadow ledger checkpoint, and the durable learned posture state.

That executor must explicitly preserve/reconcile `pending_buy` and
`position_action_states` so deferred BUY/REDUCE/SELL work cannot be replayed
or silently lost across restart.
