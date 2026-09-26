# Fast PAPER Shadow Runtime State — Design

**Date:** 2026-09-26  
**Base main SHA:** `c110dfaad9fb0d8bc4c88c3231be85b1cd88ef47`

## Purpose

Add the smallest durable state boundary required before the learned shadow
service may execute `BUY/HOLD/REDUCE/SELL`.

The existing isolated shadow-ledger checkpoint preserves the canonical
`PaperLedger`, Fast PAPER event-loop state, pending BUY authority, and
position-action state. It does **not** preserve the learned continuous-action
exposure fraction associated with each open market. That exposure is required
to construct an exact
`FastCampaignDecisionPosition(kind="OPEN", current_exposure_fraction=...)`
after restart.

The runtime must not infer learned exposure from ledger notional, mark price,
position quantity, environment variables, or current quotes. Those values are
not the learned action-policy exposure state.

## State contract

Add a manifest/binding/checkpoint-authenticated companion state in the same
isolated shadow-ledger SQLite database.

Each open learned market mapping contains exactly:

- `market_key`;
- canonical `position_id`;
- canonical position `mint`;
- learned `current_exposure_fraction` in `(0, 1]`.

The state also binds:

- exact shadow-ledger binding fingerprint;
- exact canonical Fast PAPER checkpoint sequence;
- exact canonical Fast PAPER checkpoint payload SHA-256;
- optional last processed learned decision source sequence;
- optional last processed learned decision source event identity;
- optional last processed learned decision-evidence fingerprint;
- deterministic state fingerprint.

The last-decision fields are all-or-none.

## Ledger consistency

For every saved or loaded state:

- every canonical OPEN `PaperLedger` position is mapped exactly once;
- every mapping points to an existing OPEN position;
- mapping mint equals canonical position mint;
- market keys are unique;
- position IDs are unique;
- mappings use canonical ordering;
- no mapping may be synthesized for a flat ledger.

A lookup helper may return a learned `FLAT` position only when the market is
absent from the authenticated mapping. It returns `OPEN` only from persisted
exposure authority.

## Atomicity and torn-state rule

The companion state is keyed by the exact canonical paper-checkpoint sequence.
It may be saved only against the latest persisted shadow-ledger checkpoint.

Loading fails closed if the canonical paper checkpoint has advanced without a
matching companion runtime-state row. This prevents a restart from combining a
new ledger with stale learned exposure state.

The companion payload is canonical, fingerprinted, append-only per checkpoint
sequence, idempotent for an exact repeat, and stored only in the already
isolated private shadow-ledger database.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
AUTHORITATIVE_PAPER_EVIDENCE=UNCHANGED
SHADOW_LEDGER_STATE=ISOLATED_DURABLE
SHADOW_LEARNED_POSTURE_STATE=ISOLATED_DURABLE
SHADOW_EXECUTION=NOT_GRANTED
SHADOW_SERVICE_INTEGRATION=DEFERRED
RISK_POLICY_PARAMETER_AUTHORITY=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

This slice must not import or invoke BUY/position execution, scoring, provider
network clients, signing/submission, future labels, or counterfactual modules.

## Follow-on

After this state is durable and restart-safe, a separate reviewed slice may
bind exact risk/fill/entry-authority inputs and apply learned decisions to the
isolated shadow ledger. That later slice can derive truthful `FLAT/OPEN`
posture from this state rather than inventing it.
