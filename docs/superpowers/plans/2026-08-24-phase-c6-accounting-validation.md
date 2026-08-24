# Phase C6 Accounting Validation and Restart Recovery Verification Record

**Goal:** Prove Phase C accounting and restart integrity without changing trading logic.

**Base:** verified C5 head `7f9e0b2e163e1f4c22855d9a14ecdadccdde5bea`.

**Design:** `docs/superpowers/specs/2026-08-24-phase-c6-accounting-validation-design.md`.

## Completed contract

C6 adds independent validation and durable restart recovery around the already-sealed C1/C3/C4/C5 paper path.

It:

- independently recomputes portfolio cash, realized PnL, accumulated costs, lifecycle-linked economics, running quantities, marked market value, equity, and net PnL from authoritative C3 evidence;
- reports missing OPEN-position marks as `INCOMPLETE` rather than inventing zero unrealized PnL;
- reports contradictory accounting as `INVALID` rather than repairing or silently accepting it;
- records explicit evidence counts for partial reductions, terminal execution failures, total/open/closed lifecycles, and winning/losing/flat closed lifecycles;
- adds Rust-owned SQLite migration 0006 with append-only `paper_loop_checkpoints` rows and a deterministic latest-checkpoint index;
- keeps Python from creating or migrating the table itself; an unmigrated operational database fails closed;
- serializes only an explicit allow-list of immutable C3/C4/C5/B9 state types and enums using canonical JSON, exact hexadecimal finite floats, deterministic tuples/frozensets, and SHA-256 integrity;
- uses no pickle, eval, dynamic imports, arbitrary class paths, or executable deserialization;
- rejects unknown tags, malformed field sets, checksum corruption, row/envelope metadata divergence, sequence collisions, and non-monotonic new checkpoints;
- makes an identical run/sequence/payload save idempotent while preserving append-only history;
- restores exact `PaperLoopState` from a fresh SQLite connection and validates state equality, canonical fingerprint equality, and accounting equality;
- proves duplicate terminal C3 intent protection still holds after restore;
- proves C5 can continue from restored state and independently advance multiple OPEN-position marks;
- exposes an exact 13-symbol `shreks_brain.paper_validation` public API;
- changes no C1 fill math, C3 accounting math, C4 exit rules, C5 trading decisions, provider logic, signer, transaction submission, or live-money authority.

## TDD and verification evidence

### Gate 1 — schema and independent accounting validator

- RED `8192568b03846378dc5957d21139631a1fb23ee1` / CI `32720175022`: Python failed only because `shreks_brain.paper_validation` did not yet exist; Rust failed only because schema version 6 and `paper_loop_checkpoints` did not yet exist; repository safety was green.
- Initial implementation `295f50a27211f9308e456394883f19831bfbadf9` / CI `32721151417` added migration 0006 and the validator. The run exposed test-side exact-float expectations plus legacy tests that hard-coded the previous latest schema version.
- Accounting expectation correction `7c7c00fbec7bb81833b4a2b9255ec7f8fae13164` / CI `32721281364`: Python and repository safety green; the only Rust issue was a stale schema-version assertion.
- Legacy schema assertions were aligned at `cd61342e2c6e87793f68af6cd76cdf90ee159260` and `d0c8595250b5e1b13d1d4b9cb1870072dcaa2076`. Migration 0006 itself was already passing.

### Gate 2 — canonical checkpoint codec and restart recovery

- RED `e6eb17d3d8999adc0611909c0009517ff78fa1fc` / CI `32721690322`: exact missing `PaperCheckpointError`/checkpoint API surface; repository safety green.
- Checkpoint/restart models `f180465931ff56e0e88768fd746bb03c9de30c83` pinned schema `c6-paper-state-v1` and immutable checkpoint/restart reports.
- GREEN implementation `6d8a4e73b5529048d6357ff61697c375a4e9429a` / CI `32722061243`: canonical allow-listed codec, SHA-256 verification, append-only SQLite save/load, collision/monotonicity protection, and restart-equivalence validation. Python and repository safety were green on that run; the later full-stack Gate 3 run proves the combined Rust/Python head.

### Gate 3 — source-required accounting/restart scenario and public API

- Scenario/API `8963b28a6ff438e28c00d47eb49fd9cfecca8db9` / CI `32722296257`: Python, Rust/workspace metadata, and repository safety all green.
- The scenario contains four lifecycles in one authoritative history: a winning closed lifecycle with a genuine partial reduction, a losing closed lifecycle with a failed-after-submission network cost, and two simultaneous OPEN positions.
- It validates marked equity, checkpoints to file-backed SQLite, reopens through a fresh connection, proves exact restart equivalence, rejects replay of an already-terminal intent without changing the ledger, continues through C5 after restore, advances both OPEN marks independently, writes a later checkpoint, reloads the latest state, and reconciles accounting again.
- The stable public API is exactly:

```text
AccountingFinding
AccountingFindingCode
AccountingValidationReport
AccountingValidationStatus
PaperCheckpointError
PaperCheckpointRecord
RestartValidationReport
decode_paper_checkpoint
encode_paper_checkpoint
load_latest_paper_checkpoint
save_paper_checkpoint
validate_paper_accounting
validate_restart_equivalence
```

## Phase C boundary

C6 proves the accounting/restart mechanics required for extended realistic PAPER operation. It does **not** claim that any strategy is profitable, does not supply production thresholds or capital settings, and does not authorize live trading. Promotion still requires extended unseen paper evidence with positive expectancy after realistic costs, acceptable drawdown, stable providers/restarts, reproducible evaluation, and no unresolved accounting/execution defect.

The final exact-head SHA and final CI run are recorded only in draft PR metadata after the branch is frozen, not in this tracked verification file.
