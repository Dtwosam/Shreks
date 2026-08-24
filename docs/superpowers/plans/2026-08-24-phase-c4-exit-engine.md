# Phase C4 Exit Engine Verification Record

**Predecessor:** verified C3 head `7393575e6b54033b335becaa484cf4a992857bc9`.

**Goal:** add a deterministic, point-in-time position exit layer that emits `HOLD / REDUCE / EXIT` with exact target quantity, structured reasons, high-water/take-profit state, and no execution authority.

## Architecture

- New pure Python package: `shreks_brain.exits`.
- Reuses unchanged B2 `b2-v1` `FeatureVector` for price/liquidity/flow/momentum evidence.
- Reuses C3 `PaperPosition` as authoritative position quantity, weighted entry, lifecycle, and booked holdings truth.
- Adds only immutable, size-aware exit execution evidence (`route_state`, available exit notional, impact percentage + covered notional, optional wallet-distribution evidence, global halt).
- Uses existing `DecisionAction.HOLD / REDUCE / EXIT`; B8 entry behavior is unchanged.
- No production `ExitPolicy` defaults or production thresholds.
- No provider/storage/wall-clock/RNG reads inside exit logic.
- No SELL `TradeIntent` construction in C4. The shared intent is USD-notional based, so converting an exact quantity reduction into a fixed decision-time notional could oversell after price movement. C5 owns quote-aware wiring through the existing `TradeIntent -> C1 realistic execution -> C3 accounting` path.
- No C1 execution change, C3 accounting change, wallet reconstruction, persistence, signer, transaction construction/submission, or live-money path.

## Deterministic behavior

Structural/schema/state/time contradictions fail closed to `HOLD`. Once structurally coherent, global halt and maximum hold may demand a full `EXIT` even when current price/market/execution evidence is stale or missing. With usable evidence, fixed primary precedence is:

```text
liquidity route unavailable
liquidity below minimum
exit price impact too high
exit capacity too low
hard stop
trailing stop
explicit wallet distribution
flow deterioration
momentum deterioration
take profit
no exit -> HOLD
```

Every assessment has exactly one primary reason and retains simultaneous lower-priority proven triggers as supporting findings. Equality at configured boundaries triggers deterministically with a fixed arithmetic tolerance.

High-water state never decreases and advances only on usable point-in-time evidence. The earliest incomplete take-profit level is the only profit-taking level eligible to fire. `acknowledge_exit_fill` marks a level complete only when authoritative C3 before/after quantity evidence proves the booked reduction reached the decision target (or the position fully closed); failed/no-fill/undersized partial outcomes do not advance the ladder.

Wallet-distribution evidence stays tri-state. Unknown is never converted to false or treated as a trigger. C4 does not fabricate Phase D wallet intelligence.

## Stable public API

`shreks_brain.exits` exports exactly:

```text
ExitAssessment
ExitExecutionContext
ExitFinding
ExitPolicy
ExitReasonCode
ExitRouteState
ExitState
TakeProfitLevel
acknowledge_exit_fill
assess_exit
create_exit_state
```

The public surface carries no `TradeIntent`, quote/fill authority, signer, wallet secret, transaction, provider, persistence, or live-execution authority.

## TDD evidence

- Domain RED: `747fc80036e499826cc41c0fedc2306d5c7b115a` / CI `32675150122` — expected missing `shreks_brain.exits` failure.
- Domain GREEN: `8fa1e20edd820ae70066dd4211448dd34354e057` / CI `32675207813` — Rust, Python, workspace metadata, repository safety green.
- Exit-engine RED: `4ddfefaf8bb63c8af130cba64b82b14aa289fc11` / CI `32675346042` — expected missing `shreks_brain.exits.engine` failure.
- Chronology representation correction: `7d883a7f114756ac8c6de11c5d2b235f6d123f30` — invalid pre-position chronology preserves unknown position age instead of fabricating zero.
- Initial engine GREEN diagnostic: `3d9c5bb48964b1f1b23b8b1fe67a9904ac116af8` / CI `32710551377` — 1,342 tests passed; five C4 failures exposed structural-mismatch output representation plus floating-point equality semantics.
- Structural contradiction representation fix: `4662839983eab38c45fd639634ae99cebe3e9369`.
- Exit-engine final GREEN: `57adf45971e188e3aafa81af4a0389bb37f11bbf` / CI `32710816118` — all checks green with fixed `1e-12` threshold-comparison tolerance.
- Fill-acknowledgement RED: `81c59ec4c36745702ded75c795a8bc3141311daf` / CI `32711003373` — expected missing `acknowledge_exit_fill` failure.
- Fill-acknowledgement GREEN: `dcf1225a67232973bdae548f4a075bd1c0ec899b` / CI `32711283434` — all checks green.
- Public-API RED: `98dbe5d62099c50c101c256d3ab33a1b2ac487e6` / CI `32711438463` — expected package-level export failure.
- Public-API GREEN: `d3268d0649ff6d50725fb114f66b2022bf9c973d` / CI `32711500520` — all checks green.
- README semantics commit: `50fa55e5f160110525c07f9327adb012e648dbb0`.

## Intended C3 -> C4 diff

Exactly these files are allowed:

```text
README.md
docs/superpowers/plans/2026-08-24-phase-c4-exit-engine.md
docs/superpowers/specs/2026-08-24-phase-c4-exit-engine-design.md
python/src/shreks_brain/exits/__init__.py
python/src/shreks_brain/exits/models.py
python/src/shreks_brain/exits/engine.py
python/tests/test_exit_models.py
python/tests/test_exit_engine.py
python/tests/test_exit_acknowledgement.py
python/tests/test_exit_public_api.py
```

No B2, B8, risk, C1 execution, C3 accounting, Rust/storage/provider, signer, transaction, or live-execution implementation file may change.

This record intentionally does not contain the final C4 branch SHA or final CI run. After this record commit, the branch must be frozen; the immutable final head/run belongs only in PR metadata after exact-head CI and diff verification.