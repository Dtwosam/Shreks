# Fast PAPER Shadow Execution Join Telemetry — Design

**Date:** 2026-09-27  
**Base main SHA:** `360fc14b621262c6a4c24554ee84f8b65b7728c3`

## Purpose

Add the fresh-decision execution-source join half of FL10.2 telemetry.

This slice authenticates one persisted learned decision, its immutable execution
source record, the exact historical isolated PAPER checkpoint/runtime-state pair
that the source record was built against, and the exact successor checkpoint
that was committed after executing it.

The telemetry path reconstructs the transition through the existing sealed
Fast PAPER execution logic in **read-only historical reconstruction mode** and
requires the reconstructed next state to equal the actual durable successor
state before any latency, cost, fill, or abort metric is emitted.

This slice does not add execution authority, checkpoint writes, service
activation, signing, submission, or LIVE authority.

Pending-BUY retry source joins remain a following slice because they use a
separate persisted source schema and retry transaction.

## Historical read primitives

Add exact read-only loaders:

```python
load_fast_paper_checkpoint_by_sequence(
    database_path,
    run_id,
    sequence,
) -> FastPaperCheckpointRecord | None

load_fast_paper_shadow_ledger_checkpoint_by_sequence(
    manifest,
    binding,
    *,
    sequence,
) -> FastPaperCheckpointRecord | None

load_fast_paper_shadow_runtime_state_by_checkpoint_sequence(
    manifest,
    binding,
    *,
    sequence,
) -> FastPaperShadowRuntimeState | None
```

They must:

- perform no writes;
- preserve the existing canonical JSON/checksum/fingerprint validation;
- preserve persisted shadow-ledger binding authentication;
- validate the runtime state against the exact historical checkpoint;
- reject row/payload metadata drift.

## Read-only historical reconstruction

Refactor the existing shadow executor so production execution still requires the
exact latest durable checkpoint/runtime pair, while exposing one pure helper:

```python
reconstruct_fast_paper_shadow_decision(
    manifest,
    execution_policy,
    binding,
    paper_checkpoint,
    shadow_state,
    source,
) -> FastPaperShadowExecutionTransition
```

The helper:

- performs the same static manifest/policy/binding/checkpoint/runtime/source
  consistency checks as the production executor;
- does not require the supplied pair to be the latest pair;
- performs no storage/network/system mutation;
- reuses the same `execute_fast_paper_buy(...)`,
  `apply_fast_paper_position_action(...)`, and event-loop logic;
- returns the same immutable transition shape.

The production `execute_fast_paper_shadow_decision(...)` remains unchanged in
authority: it first requires the exact latest durable pair, then delegates to
the pure reconstruction core.

## CLI

Add:

```text
shreks-fast-paper-shadow-execution-telemetry summarize \
  --manifest-path <path> \
  --execution-policy-path <path> \
  --ledger-database-path <path> \
  --run-id <id> \
  --decision-evidence-directory <path> \
  --execution-source-directory <path> \
  --expected-release-sha <40-hex> \
  --since-unix-ms <inclusive> \
  --until-unix-ms <exclusive>
```

Window rules are exact non-negative integer milliseconds, `since < until`,
maximum 24 hours.

The action window is keyed by
`FastPaperShadowDecisionEvidence.evaluated_at_unix_ms`.

## Join procedure

For each decision-evidence record in the requested window:

1. authenticate the decision evidence;
2. require release/manifest/champion/action-policy bindings;
3. locate the immutable execution-source file by the decision evidence
   fingerprint;
4. read only the source record's checkpoint/runtime binding metadata;
5. load the exact historical pre-execution checkpoint by source sequence;
6. load the exact historical runtime state for that checkpoint;
7. authenticate the full execution-source record through the existing source
   reader using those exact identities;
8. reconstruct the execution transition through the sealed read-only historical
   executor;
9. load the exact successor checkpoint/runtime state at
   `pre_checkpoint.sequence + 1`;
10. require:
    - successor PAPER state equals reconstructed `next_paper_state`;
    - successor runtime state binds the successor checkpoint;
    - successor market positions/pending BUY/execution policy equal the
      reconstructed transition;
    - successor last-processed source identity equals the decision;
11. only then emit telemetry for that joined action.

Missing source/successor evidence is counted as incomplete evidence and does not
produce a fabricated outcome.

## Metrics

### Coverage

Expose:

- decisions in requested window;
- joined executions;
- missing execution-source count;
- missing successor-commit count.

### Action and outcome

Expose exact action counts for:

- BUY;
- SKIP;
- HOLD;
- REDUCE;
- SELL.

Expose reconstructed outcome counts using the existing result enums.

SKIP has outcome `SKIP`.

### Latency

For every joined action:

```text
decision_to_commit_latency_ms =
    successor_checkpoint.created_at_unix_ms
    - decision_evidence.evaluated_at_unix_ms
```

Require non-negative latency.

For executions that produced a new terminal ledger entry:

```text
decision_to_booked_entry_latency_ms =
    new_entry.booked_at_unix_ms
    - decision_evidence.evaluated_at_unix_ms
```

Expose deterministic mean/p50/p95 for both latency families.

### Price execution cost

For BUY:

- expected selected price cost =
  `decision_evidence.entry_execution_cost_bps`.

For SELL:

- expected selected price cost =
  `decision_evidence.exit_execution_cost_bps`.

For REDUCE:

- expected selected price cost is the exact
  `constraints.reduce_execution_costs` member matching the selected target
  exposure.

For SKIP/HOLD, expected selected price cost is `null`.

For a filled reconstructed execution, realized price cost is the sealed
`PaperFill.signed_slippage_bps`.

Expose paired mean/p50/p95 of:

- expected selected price cost bps;
- realized price cost bps;
- realized minus expected price-cost delta bps.

Do **not** fold explicit fees into that comparison.

Separately expose realized explicit fee/network cost bps:

```text
explicit_cost_usd / filled_notional_usd * 10_000
```

and realized total execution burden bps:

```text
signed_slippage_bps + explicit_cost_bps
```

### Abort/rejection attribution

Because the outcome is reconstructed through the sealed execution path, expose
exact counts for fresh-decision outcomes including:

BUY:
- `DEFERRED`;
- `ABORTED_QUOTE_UNAVAILABLE`;
- `ABORTED_QUOTE_TOO_LATE`;
- `ABORTED_PRICE_ABOVE_MAXIMUM`;
- `ABORTED_INSUFFICIENT_CAPACITY`;
- `RISK_REJECTED`;
- `ABORTED_TOTAL_COST_ABOVE_MAXIMUM`;
- `EXECUTION_FAILED`;
- `FILLED`;
- `LEDGER_REJECTED`.

Position actions use the existing `FastPaperPositionOutcome` enum.

Expose a dedicated `max_entry_price_abort_count` derived only from
`ABORTED_PRICE_ABOVE_MAXIMUM`.

## Output/provenance

Emit canonical JSON with:

- release SHA;
- manifest fingerprint;
- champion version/fingerprint;
- action-policy version;
- execution-policy fingerprint;
- run id and shadow-ledger binding fingerprint;
- requested window;
- counts/summaries above;
- telemetry fingerprint.

## Authority firewall

The telemetry module may call the read-only reconstruction helper, but must not:

- call production service execution functions;
- commit/save/write checkpoints or runtime state;
- write source/decision evidence;
- use systemd/subprocess/network clients;
- sign/submit;
- enable LIVE.

The executor refactor must not weaken the existing production latest-state gate.

## RED acceptance

Tests prove:

1. exact checkpoint-by-sequence reads are canonical/checksum safe;
2. exact historical runtime-state reads authenticate row/payload/checkpoint;
3. production executor still rejects stale historical pairs;
4. read-only reconstruction accepts the same authenticated stale pair and
   produces the exact original transition;
5. a persisted BUY fill joins pre-state -> source -> reconstructed transition ->
   successor state exactly;
6. commit and booked-entry latency are exact;
7. expected decision price cost and realized fill slippage are compared using
   like-for-like bps;
8. explicit cost and total realized execution burden are separate;
9. a persisted BUY maximum-entry-price abort is attributed exactly without a
   fabricated ledger fill;
10. tampered source/checkpoint/runtime/successor evidence fails closed;
11. missing source/successor evidence is counted incomplete;
12. output is canonical and fingerprinted;
13. CLI is packaged;
14. no new execution/storage/system/LIVE authority is introduced.

## Following slice

Add pending-BUY retry source joins and then adapt operator dashboard surfaces to
the combined Fast Lane decision + outcome + latency/cost telemetry.

Physical-host shadow evidence still does not grant production PAPER cutover or
LIVE authority.
