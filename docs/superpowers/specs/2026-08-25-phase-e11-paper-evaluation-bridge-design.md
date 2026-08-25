# Phase E11 Paper Evaluation Bridge Design

## Purpose

Phase E11 closes the proof-path gap between sealed C1/C3/C5 paper execution and sealed E5/E10 trading evaluation.

E5 deliberately refuses to invent fills. It requires caller-supplied closed-trade economics after realistic execution friction and explicit costs. C1 already simulates quote/reference price, execution price, slippage, partial fills, swap fees, and network fees. C3 keeps authoritative accounting, and C5 carries setup/regime decision provenance. However, the long-lived C3 ledger intentionally drops C1 reference-price/slippage detail and C5 setup/regime detail. Reconstructing those fields later from the ledger alone would require guessing.

E11 records the missing paper-evaluation provenance at the moment C5 produces it, preserves it across restart, and converts only fully reconciled closed paper positions into sealed E5 `EvaluatedTrade` values.

E11 is based exactly on sealed E10 head `f31d34382170b3fac8d5073299c8ef2e7e81b8ca`.

## Source-of-truth alignment

The master learning loop requires:

```text
... VALIDATE -> PAPER/SHADOW -> COMPARE -> PROMOTE OR REJECT
```

The live gate requires realistic fill simulation, reproducible evaluation, acceptable drawdown, positive expectancy after realistic costs, restart stability, and no unresolved accounting/execution defects.

E11 exists to make paper outcomes usable as truthful E5 evidence. It does not relax any live gate and does not enable live execution.

## Core boundary

The runtime capture path is:

```text
RegistryCandidate + C5 PaperCycleResult
  -> capture entry provenance before it can be lost
  -> capture every terminal booked paper execution linked to a position
  -> capture authoritative closed-position snapshot
  -> append canonical evidence events
```

The evaluation path is:

```text
persisted E11 evidence
  -> reconcile candidate + strategy + intent + ledger sequence
  -> reconcile entry provenance + all linked execution costs
  -> reconcile final C3 closed-position accounting
  -> normalize one E5 EvaluatedTrade per complete closed position
  -> caller may append resulting trades to sealed E10 evidence store
```

E11 never derives economics from D6 future-return labels and never fabricates missing setup, regime, fill, cost, or closure evidence.

## Package

Create `shreks_brain.paper_evaluation` with schema version:

```text
e11-paper-evaluation-v1
```

Suggested files:

- `paper_evaluation/models.py` — immutable evidence contracts and invariants;
- `paper_evaluation/engine.py` — extract C5 cycle evidence and normalize complete positions to E5 trades;
- `paper_evaluation/codec.py` — exact canonical JSON mapping and fingerprinting;
- `paper_evaluation/store.py` — restart-safe append-only evidence store;
- `paper_evaluation/__init__.py` — explicit public API.

Do not change sealed C1, C3, C5, C6, E5, E6, E7, E8, E9, or E10 behavior.

## Run identity

Every E11 capture requires an explicit non-empty `paper_run_id` supplied by the caller.

C3 ledger sequence values restart at 1 for a fresh ledger, so a run id is required to make evidence identities globally unambiguous. E11 does not infer run identity from wall-clock time, file paths, or starting capital.

## Candidate identity

Cycle capture receives an exact E6 `RegistryCandidate`, not a free-form candidate-version string.

E11 records:

- `candidate_version`;
- `candidate_fingerprint_sha256`;
- `strategy_version`.

Every booked C3 ledger entry captured for that candidate must have `strategy_version` equal to the registry candidate's strategy version. A mismatch fails closed.

E11 does not require the candidate to be CHALLENGER or CHAMPION; registry status remains an E6/E8 concern. It only verifies attribution.

## Evidence model

E11 stores three immutable evidence families plus explicitly tracked orphan-cost events.

### 1. `PaperEntryProvenance`

Captured whenever C5 selects an entry and creates a `PaperExecutionResult`, including a DEFERRED result before a position exists.

Fields:

- `paper_run_id`;
- candidate version/fingerprint/strategy version;
- entry intent idempotency key;
- mint;
- decision timestamp;
- setup name;
- market regime;
- score policy version;
- decision policy version;
- paper execution policy version.

The setup/regime values come directly from the frozen entry `ScoreAssessment`/`TradeDecision`. They may not be reconstructed later from token history.

Identity is `(paper_run_id, intent_idempotency_key)`. Same identity/content is idempotent; conflicting content fails closed.

### 2. `PaperPositionExecutionEvidence`

Captured only when a terminal C1 execution was actually booked into C3 and has a non-null `position_id`.

Fields preserve the exact evidence needed for economic normalization and reconciliation:

- run/candidate/strategy identity;
- position id;
- C3 journal sequence;
- intent idempotency key;
- mint and side;
- execution state;
- ledger reason code;
- booked/evaluated timestamps;
- requested notional;
- explicit cost;
- fill presence;
- when filled: filled notional, quantity, reference price, execution price, signed slippage USD, quote provider, executed timestamp.

FAILED executions linked to an already-open position are recorded even when there is no fill because a simulated failed submission may still incur a network cost that C3 books into realized PnL.

Identity is `(paper_run_id, ledger_sequence)`. Ledger sequences must be strictly increasing within a run and cannot map to conflicting content.

### 3. `PaperClosedPositionEvidence`

Captured when C3 reports `POSITION_CLOSED`.

Fields:

- run/candidate identity;
- position id and mint;
- authoritative opened/closed timestamps;
- final realized PnL;
- final accumulated explicit costs;
- buy fill count;
- sell fill count;
- closing ledger sequence.

This snapshot is not an alternate ledger. It is the minimum immutable terminal accounting evidence needed to verify later E5 normalization against the sealed C3 result.

Identity is `(paper_run_id, position_id)` and is immutable/idempotent.

### 4. `PaperOrphanCostEvidence`

A failed entry can incur a simulated network fee before any position exists. Such a cost is real paper execution cost but cannot honestly be attached to an E5 `EvaluatedTrade` because no position was opened.

E11 therefore records positive terminal failed-entry costs separately with:

- run/candidate identity;
- intent idempotency key;
- mint;
- explicit cost;
- evaluated timestamp.

E11 never silently allocates this cost to another trade.

## Cycle extraction

Public pure function:

```python
extract_paper_evaluation_evidence(
    paper_run_id: str,
    candidate: RegistryCandidate,
    cycle: PaperCycleResult,
) -> PaperEvaluationCapture
```

`PaperEvaluationCapture` contains tuples of new entry provenance, position execution evidence, closure evidence, and orphan costs.

Extraction inspects:

- `pending_entry_result`;
- `entry_results`;
- `exit_results`;
- each result's execution and applied ledger update;
- the final `next_state.ledger` position state.

Rules:

- DEFERRED selected entries create/refresh only idempotent entry provenance, never execution evidence;
- terminal entry fills with an applied ledger update create position execution evidence;
- terminal exit fills/reductions/closures create position execution evidence;
- terminal failed exits that C3 books against an open position are captured so their costs reconcile;
- failed entries with positive booked cost and no position create orphan-cost evidence;
- rejected/no-op ledger updates do not become economic evidence;
- evidence is returned in deterministic journal order.

## Deferred-entry provenance

C5 intentionally keeps a pending entry intent across cycles but its pending object does not retain setup/regime. Therefore E11 must be active on the original cycle that selected the entry.

If a later pending-entry terminal booking is observed without previously captured entry provenance for that intent, E11 stores the execution evidence but the position remains **not evaluable**. It must not guess setup/regime from the mint or a later row.

This fail-closed behavior means a paper run intended for promotion evidence should start E11 capture before new entries are allowed.

## E5 normalization

Public pure function:

```python
build_evaluated_trades(
    paper_run_id: str,
    candidate_version: str,
    entry_provenance: tuple[PaperEntryProvenance, ...],
    executions: tuple[PaperPositionExecutionEvidence, ...],
    closures: tuple[PaperClosedPositionEvidence, ...],
    orphan_costs: tuple[PaperOrphanCostEvidence, ...],
) -> tuple[EvaluatedTrade, ...]
```

Only complete closed positions for the requested candidate are emitted.

For each closed position:

```text
entry_notional_usd = sum(successful BUY filled_notional_usd)
turnover_usd = sum(all successful BUY/SELL filled_notional_usd)
execution_friction_usd = sum(max(0, signed_slippage_usd) for successful fills)
explicit_cost_usd = sum(explicit_cost_usd for every booked execution linked to position)
net_pnl_usd = authoritative C3 closed-position realized_pnl_usd
gross_pnl_usd = net_pnl_usd + execution_friction_usd + explicit_cost_usd
```

The E11 `gross_pnl_usd` is therefore the normalized result before **adverse** simulated execution friction and explicit costs. Favorable signed slippage is not turned into a negative cost; its benefit remains embedded in the gross result. This preserves E5's non-negative execution-friction contract while keeping arithmetic exact.

The adapter requires:

```text
net_pnl_usd == gross_pnl_usd - execution_friction_usd - explicit_cost_usd
```

within the same strict numerical tolerance used by sealed accounting/evaluation layers.

## Reconciliation gates

A position is rejected from evaluation by raising an error if any of these fail:

- missing entry provenance;
- candidate/fingerprint/strategy mismatch across evidence;
- mint mismatch;
- entry intent does not correspond to the BUY execution that opened the position;
- duplicate or non-increasing ledger sequence;
- no successful BUY fill;
- no successful SELL fill;
- successful BUY/SELL fill counts do not equal final C3 fill counts;
- summed explicit costs do not equal final C3 accumulated costs;
- final closure time/order is inconsistent with executions;
- entry notional or turnover is non-positive;
- any derived value is non-finite;
- any E5 `EvaluatedTrade` invariant fails.

Incomplete open positions are ignored because they are not closed-trade evidence yet.

## Orphan-cost fail-closed rule

If the requested candidate/run contains any positive `PaperOrphanCostEvidence`, `build_evaluated_trades(...)` fails closed.

Reason: emitting otherwise-profitable trades while dropping real simulated submission costs would overstate expectancy. E5-v1 has no run-level cost field for a cost not attributable to a position. E11 will not silently allocate it.

A later phase may add a run-level evaluation-cost contract if real data shows this path matters; E11-v1 prefers no result over a biased one.

## Persistence

`PaperEvaluationEvidenceStore(path)` exposes only:

```text
load() -> PaperEvaluationLedger
record_capture(capture) -> PaperEvaluationLedger
record_cycle(paper_run_id, candidate, cycle) -> PaperEvaluationLedger
evaluated_trades(paper_run_id, candidate_version) -> tuple[EvaluatedTrade, ...]
```

The physical document is canonical JSON with exact schema validation. It stores append-only evidence arrays and a document fingerprint over the complete canonical content.

Writes use the sealed E6-E10 pattern:

1. create parent directories;
2. write `<name>.tmp` using UTF-8 and one trailing newline;
3. flush and `os.fsync`;
4. atomic `os.replace`;
5. best-effort temporary cleanup on error.

Load independently reconstructs immutable evidence objects, recomputes the document fingerprint, checks identities/order, and fails closed on corruption.

## Canonical ordering

- entry provenance: `(paper_run_id, decision_as_of_unix_ms, intent_idempotency_key)`;
- execution evidence: `(paper_run_id, ledger_sequence)`;
- closures: `(paper_run_id, closed_at_unix_ms, position_id)`;
- orphan costs: `(paper_run_id, evaluated_at_unix_ms, intent_idempotency_key)`.

Store writes canonical order. Decode rejects non-canonical persisted order rather than silently sorting tampered documents.

## Relationship to E10

E11 does not automatically create an E5 report or E10 record.

The explicit composition is:

```text
E11 evaluated_trades(...)
  + caller-supplied mature E4 probability observations
  + caller-supplied E5 policy
  -> E10 append(...)
```

This keeps candidate economics, model calibration, and evaluation policy separate and auditable.

## Authority firewall

E11 exposes no method to:

- mutate E6 registry status;
- evaluate or record E8 promotion;
- alter C5 paper decisions;
- generate a new `TradeIntent`;
- execute paper or live fills;
- sign or submit transactions;
- enable LIVE mode;
- choose live-capital limits.

It only captures already-produced paper evidence and normalizes complete closed paper positions for E5.

## Explicit non-goals

E11 does not:

- change the paper fill simulator;
- change paper accounting;
- invent missing setup/regime provenance;
- infer historical quote/reference prices;
- allocate orphan failed-entry costs to unrelated positions;
- score probability calibration;
- choose a candidate or promotion threshold;
- claim profitability;
- start Phase F.

## Exit criterion

E11 is complete when a fresh paper run can survive process restarts while preserving enough C5/C1/C3 provenance to convert every fully reconciled closed paper position into deterministic E5 `EvaluatedTrade` evidence, while failing closed whenever missing provenance or unattributed execution costs would bias the result.