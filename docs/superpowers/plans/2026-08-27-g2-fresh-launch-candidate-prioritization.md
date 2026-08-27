# G2 production PAPER fix — Fresh Launch candidate prioritization

Date: 2026-08-27

## Physical PAPER evidence

The dedicated production VPS was running immutable release `27c4ce4ae319033d88890a5b1a6c0b9362cf429d` continuously and restart-safely. Physical host proof showed 58 consecutive post-deploy checkpoints, sequence 57 through 114, at approximately the configured 30-second cadence, with zero campaign restarts and all Shreks services active.

A read-only PAPER evaluation showed zero entry provenance, zero executions, zero closed positions, and zero evaluated trades. The current two selected candidates were rejected before execution and were already far outside the Fresh Launch setup window.

A read-only 30-minute candidate cohort then showed:

- 101 recently observed candidates;
- 7 candidates inside the configured 60-second to 30-minute Fresh Launch window;
- 29 candidates younger than 60 seconds;
- 65 candidates older than 30 minutes;
- 1 fresh candidate passing the four basic liquidity/flow checks used in the diagnostic;
- both existing selector slots occupied by expired tokens, so `CURRENT_TOP2_INSIDE_FRESH_WINDOW=0`;
- `FRESH_EXIST_BUT_SELECTOR_MISSES=True`.

This proved a candidate-universe mismatch rather than a reason to loosen strategy or safety thresholds.

## Root cause

The generic campaign selector ranked regular candidates by newest market observation within its recent-observation lookback. The Fresh Launch strategy, however, hard-blocks candidates older than its configured maximum token age. A frequently observed old token could therefore consume one of the small number of new-entry candidate slots even though it could never become an ENTER under the active setup policy.

## Corrected behavior

For regular new-entry selection in the Fresh Launch campaign:

- pair age is derived from persisted `pair_created_at_unix_ms` evidence at the cycle point in time;
- candidates older than the existing `FreshLaunchPolicy.max_age_seconds` cannot consume regular new-entry slots;
- candidates already between the existing minimum and maximum Fresh Launch ages are prioritized;
- too-young candidates remain eligible as fallback/WATCH candidates when entry-window candidates do not fill the available slots;
- contradictory pair-creation evidence fails closed rather than being guessed;
- required mints for existing managed positions or a pending entry continue to be resolved separately and are not discarded by the regular new-entry age prioritization.

The age bounds are taken directly from the existing versioned Fresh Launch policy. No new trading threshold was introduced.

## TDD and verification evidence

Exact RED CI run: `33088606158`.

The regression failed for the intended reason with `1 failed, 2619 passed`: current behavior selected the expired candidate `(2,)` instead of the in-window candidate `(1,)`.

Final PR head: `c061c4af7b2ac4f0b4e90935d2282bcdfc848b3e`.

GREEN PR CI run: `33090441458`:

- Python GREEN: `2622 passed`;
- Rust GREEN;
- repository safety GREEN;
- native ARM64 release-build verification GREEN.

Merged behavior commit: `b685465a95725fe82948f5ea84d6370337457c23` via PR #60.

Exact merged-main CI run: `33090761891`:

- Python GREEN;
- Rust GREEN;
- repository safety GREEN;
- native ARM64 release-build verification GREEN.

## Preserved safety and authority invariants

- B1 safety vetoes remain unchanged and continue to override scoring.
- Missing or contradictory critical evidence is not guessed.
- Liquidity, flow, score, decision, risk, sizing, loss, drawdown, slippage, exit, and execution thresholds are unchanged.
- PAPER fill economics are unchanged.
- No wallet/signing/submission authority was added.
- No strategy or learning model can self-promote to LIVE.
- LIVE remains disabled.
- Profitability remains unproven until sufficient independent PAPER trades demonstrate positive expectancy after realistic costs and satisfy the existing promotion gates.

This documentation-only commit is the production release seal for the Fresh Launch candidate-prioritization correction.