# Phase C3 Paper Ledger Verification Record

> Completed implementation record for the authoritative paper position/accounting slice. Final immutable branch SHA and CI run are recorded only in PR metadata after branch freeze.

**Predecessor:** verified C1+C2 paper-execution head `bf613e727240a6eecccefe851b155029cac2398f`.

**Design:** `docs/superpowers/specs/2026-08-23-phase-c3-paper-ledger-design.md`

## Delivered architecture

- Pure, deterministic, replayable Python accounting reducer; no storage, provider, balance, wall-clock, or RNG reads.
- Immutable append-only terminal execution journal plus immutable derived position snapshots.
- `DEFERRED` C1 executions are true no-ops: no journal entry, no consumed terminal key, no accounting-time advance.
- `FAILED`, `PARTIAL`, and `FILLED` executions are terminal and can be booked at most once by intent idempotency key.
- Strong intent/result linkage and state/reason consistency checks run before any accounting mutation.
- No leverage is modeled: any terminal cash flow that would make simulated cash negative is rejected.
- Deterministic SHA-256 position lifecycle IDs; at most one OPEN lifecycle per mint; re-entry after close appends a new lifecycle and preserves closed history.
- Execution-weighted entry price excludes explicit fees; all-in open cost basis includes filled BUY notional plus incurred BUY explicit costs.
- SELL realized PnL equals net sale cash flow minus proportional all-in released open cost basis, so entry and exit costs are counted exactly once.
- Failed post-submission network costs remain visible in cash, realized PnL, accumulated costs, and the linked open lifecycle when one exists.
- Partial SELLs release open basis proportionally; full SELLs close the lifecycle while preserving historical weighted entry evidence.
- Point-in-time marks compute `quantity * mark_price - open_cost_basis`, include already-incurred entry costs, and exclude hypothetical future exit fees/slippage/liquidity.
- Aggregate unrealized PnL is zero with no OPEN positions, unknown when any OPEN position lacks a mark, otherwise the exact sum of OPEN-position unrealized PnL.
- Every ledger snapshot self-reconciles cash, realized PnL, accumulated costs, journal sequence, terminal keys, and per-position linked journal economics.
- Existing C1 public API remains intact; C3 adds exactly twelve stable ledger/position/reducer exports.
- No production starting capital, persistence, exit policy, autonomous loop, signer, transaction construction/submission, or live-money authority was added.

## TDD evidence

- Models RED: `9b2b71f839fce0fca864a7521a887a70bdc8aa26` / CI `32672127113` — Python failed only because `shreks_brain.paper.ledger_models` did not exist.
- Models initial GREEN diagnostic: `606bcd7a2f48d3de678785b336be1ab0f30cd9ba` / CI `32672198965` — 1 failed, 1298 passed because generic close-timestamp ordering fired before the stronger OPEN lifecycle contradiction; production validation precedence was corrected without weakening tests.
- Models final GREEN: `b4ecd3c100511390ee6e9fd90c3cf902c087314c` / CI `32672266889` — Rust, Python, workspace metadata, and repository safety all green.
- Terminal booking RED: `9e934e34512689e85ca565f944edfc3881351307` / CI `32674236407` — Python failed only because `shreks_brain.paper.ledger` did not exist.
- Terminal booking GREEN: `689afa291cdb8d7d14d54c35254116253ca4d811` / CI `32674304818` — full green.
- Mark-to-market RED: `b5d19c4d46c258d986e262f5f6bac87f97bf79fd` / CI `32674392823` — Python failed only because `mark_paper_position` was absent.
- Mark-to-market GREEN: `5e618afcfbf2889e07c625b618bf6a619000dc4e` / CI `32674458450` — full green.
- Public API RED: `444087fb33e062d3c3bf033c63041c02f90fcea1` / CI `32674540967` — Python failed only because C3 symbols were not exported from `shreks_brain.paper`.
- Public API GREEN: `ffc4648624f2b1c178405a7239f57f6e25a5cd2f` / CI `32674615945` — Rust, Python, workspace metadata, and repository safety all green.
- README accounting semantics: `6555711ec8e0169247429098fa9141d7a38f904a`.

## Frozen public C3 additions

`shreks_brain.paper` adds exactly:

```text
PaperLedger
PaperLedgerEntry
PaperLedgerFinding
PaperLedgerReasonCode
PaperLedgerUpdate
PaperLedgerUpdateState
PaperPosition
PaperPositionMark
PaperPositionState
apply_paper_execution
create_paper_ledger
mark_paper_position
```

Together with the ten unchanged C1 exports, the package surface contains exactly 22 symbols.

## Completion boundaries

C3 does not implement stop loss, take profit, trailing stop, max hold, emergency/liquidity exit decisions, autonomous paper looping, SQLite persistence/restart wiring, provider/RPC access, quote generation, wallet/signing, transaction construction/submission, or live trading.

The next source-order capability is C4 exit logic, which must consume authoritative OPEN-position evidence and route any eventual SELL through the existing `TradeIntent` -> realistic C1 execution -> C3 accounting path rather than create a second execution channel.
