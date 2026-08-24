# Phase D2 Wallet Trade Reconstruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministically reconstruct conservative wallet trade episodes and estimated closed outcomes from point-in-time D1 observations without hiding uncertainty.

**Architecture:** Add a pure Python `shreks_brain.wallets` package. Immutable models mirror the stable D1 observation vocabulary; one reducer sorts/deduplicates observations by local availability time and reconstructs only same-counter-asset known-inventory BUY/SELL cycles. Any inventory/economic ambiguity halts later reconstruction for that wallet/mint.

**Tech Stack:** Python 3.12+, stdlib only, immutable dataclasses, `StrEnum`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-d2-wallet-trade-reconstruction-design.md`

## Global Constraints

- Base exactly sealed D1 head `0e8872f84ef357f059c884f04f95269eb0361f6c`.
- Python owns D2 wallet intelligence; Rust D1 types/storage remain unchanged.
- `observed_at_unix_ms` is the decision-safe clock; future local observations fail closed.
- No provider/RPC/SQLite reads inside reconstruction.
- No USD/FX conversion, token-decimal guess, wallet score, profile, clustering, smart-wallet feature, strategy/risk/execution change, or live-money authority.
- Missing or contradictory economics never become zero or a guessed trade.
- TDD RED -> exact failure -> GREEN.
- Minimize CI churn: one combined RED, one focused implementation GREEN, one final exact-head seal.

---

### Task 1: Combined D2 RED contract

**Files:**
- Create: `python/tests/test_wallet_reconstruction_models.py`
- Create: `python/tests/test_wallet_trade_reconstruction.py`
- Create: `python/tests/test_wallet_reconstruction_public_api.py`

**Interfaces:**
- Consumes: no new production symbols yet.
- Produces: the exact behavioral/public contract for the D2 package.

- [ ] **Step 1: Add model RED tests**

Pin:

- exact lowercase D1 action/evidence string values,
- immutable `WalletObservation` validation,
- exact episode state/evidence-quality vocabularies,
- finding/report invariants,
- CLOSED outcome fields required together,
- OPEN/UNRESOLVED episodes cannot carry estimated realized PnL/return.

- [ ] **Step 2: Add reconstruction RED tests**

Use explicit raw-unit fixtures to require:

1. direct BUY `+100` / counter `-1000` then direct SELL `-100` / counter `+1300` => CLOSED, estimated PnL `300`, return `30%`;
2. partial sells `-40/+600` then `-60/+700` close the same 100-unit episode without proportional cost-basis invention;
3. multiple BUYs and SELLs aggregate before zero inventory closes;
4. a later BUY after clean close creates episode index 1;
5. open inventory returns OPEN with no PnL/return;
6. direct/inferred economic legs produce DIRECT/MIXED/INFERRED quality exactly;
7. input order and chain time cannot override local-observation ordering;
8. future local observation raises `ValueError` even with older chain time;
9. exact duplicate D1 identity is deduplicated and earliest local time wins;
10. contradictory duplicate identity raises `ValueError`;
11. SELL without known entry => unresolved/halt;
12. SELL beyond known inventory => unresolved/halt;
13. missing BUY/SELL economics or invalid delta directions => unresolved/halt;
14. counter-asset change inside an episode => unresolved/halt;
15. non-trade nonzero candidate delta => unresolved/halt;
16. non-trade no/zero candidate delta does not affect inventory;
17. once continuity is lost, later apparently-clean cycles are not reconstructed;
18. observations for another wallet/mint are rejected structurally.

- [ ] **Step 3: Add exact public API RED test**

Require `shreks_brain.wallets.__all__` to expose exactly:

```text
WalletActionKind
WalletObservation
WalletObservationEvidence
WalletTradeEpisode
WalletTradeEpisodeState
WalletTradeEvidenceQuality
WalletTradeFinding
WalletTradeFindingCode
WalletTradeReconstruction
reconstruct_wallet_trades
```

Also assert public dataclasses/functions expose no provider client, SQLite connection, signer, transaction, intent, fill, strategy-decision, or live-execution authority.

- [ ] **Step 4: Commit RED**

Expected CI:

- Python fails during collection because `shreks_brain.wallets` does not exist.
- Rust/workspace metadata remains GREEN.
- Repository safety remains GREEN.

Commit message: `test: define D2 wallet reconstruction contract`

---

### Task 2: Focused D2 GREEN implementation

**Files:**
- Create: `python/src/shreks_brain/wallets/models.py`
- Create: `python/src/shreks_brain/wallets/reconstruction.py`
- Create: `python/src/shreks_brain/wallets/__init__.py`

**Interfaces:**
- Consumes: caller-supplied immutable `WalletObservation` values.
- Produces: exact ten-symbol D2 public API from Task 1.

- [ ] **Step 1: Implement immutable models**

Use `@dataclass(frozen=True, slots=True)` and `StrEnum`.

`WalletObservation` mirrors D1 fields and validates identity/timestamps/optional-string pairing without interpreting action economics.

`WalletTradeEpisode` validates:

- positive bought/sold/cost/proceeds aggregates where applicable,
- `remaining_quantity_raw == total_bought_quantity_raw - total_sold_quantity_raw` for known-inventory episodes,
- CLOSED requires remaining zero, close time, counter asset, positive entry cost, and finite estimated return/PnL,
- OPEN requires positive remaining quantity and no estimated outcome,
- UNRESOLVED never carries estimated outcome.

- [ ] **Step 2: Implement deterministic normalization/deduplication**

Internal helpers:

- require all observations match requested wallet/mint,
- reject negative/future local time,
- key identity `(provider, signature, event_index, wallet, candidate_mint)`,
- identical immutable evidence deduplicates with earliest `observed_at_unix_ms`,
- contradictory duplicate raises `ValueError`,
- sort by `(observed_at_unix_ms, provider, signature, event_index)`.

- [ ] **Step 3: Implement episode reducer**

Maintain only known inventory for one active episode.

For qualifying BUY:

```text
qty = candidate_token_delta_raw > 0
cost = abs(counter_asset_delta_raw) where counter delta < 0
```

For qualifying SELL:

```text
qty = abs(candidate_token_delta_raw) where candidate delta < 0
proceeds = counter_asset_delta_raw > 0
```

Require one counter asset per episode. Accumulate raw cost/proceeds. Close only when cumulative bought quantity equals cumulative sold quantity.

On close:

```text
pnl = proceeds - cost
return_pct = (proceeds / cost - 1) * 100
```

Never emit realized outcome while remaining quantity is positive.

- [ ] **Step 4: Implement uncertainty halt**

Create the specified finding and mark the current episode UNRESOLVED (when one exists), then set `halted_on_uncertain_inventory=True` for:

- SELL without known entry,
- sell quantity greater than known inventory,
- missing economics/sign mismatch,
- counter-asset change,
- non-trade nonzero candidate-token delta.

Ignore non-trade observations with no/zero candidate-token delta for inventory arithmetic.

After halt, do not construct later episodes.

- [ ] **Step 5: Implement evidence quality**

Economic leg evidence set:

- `{direct}` => DIRECT
- `{inferred}` => INFERRED
- both => MIXED

- [ ] **Step 6: Implement exact package exports**

`__init__.py` imports only the ten approved public symbols and pins `__all__` to the exact tuple.

- [ ] **Step 7: Run full CI once**

Require Python, Rust/workspace metadata, and repository safety all GREEN on the implementation head.

Commit message: `feat: reconstruct point-in-time wallet trades`

---

### Task 3: Documentation and immutable seal

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-24-phase-d2-wallet-trade-reconstruction.md`

**Interfaces:**
- No production interface changes.

- [ ] **Step 1: Document D2 semantics in README**

Add an append-only section explaining:

- D2 consumes normalized D1 observations but performs no provider/storage reads itself,
- local observation time controls availability,
- only same-counter-asset clean inventory cycles get estimated closed outcomes,
- partial exits accumulate until zero inventory rather than inventing fractional cost allocation,
- ambiguity halts reconstruction and remains explicit,
- D2 produces no wallet score or smart-wallet feature.

- [ ] **Step 2: Replace this checklist with a concise verification record**

Record RED/GREEN evidence and scope boundaries. Do not write the eventual final SHA/run into tracked docs.

- [ ] **Step 3: Freeze branch**

No tracked writes after this commit.

- [ ] **Step 4: Audit exact D1 -> D2 diff**

Expected final files only:

```text
README.md
docs/superpowers/plans/2026-08-24-phase-d2-wallet-trade-reconstruction.md
docs/superpowers/specs/2026-08-24-phase-d2-wallet-trade-reconstruction-design.md
python/src/shreks_brain/wallets/__init__.py
python/src/shreks_brain/wallets/models.py
python/src/shreks_brain/wallets/reconstruction.py
python/tests/test_wallet_reconstruction_models.py
python/tests/test_wallet_reconstruction_public_api.py
python/tests/test_wallet_trade_reconstruction.py
```

No Rust/D1 storage, B/C trading, provider, signer, or live-execution file may change.

- [ ] **Step 5: Run one fresh exact-head full CI**

Require Python, Rust/workspace metadata, and repository safety all GREEN.

- [ ] **Step 6: Seal draft PR metadata only**

Record final SHA/run/diff in PR metadata. Leave PR draft and unmerged.

**D2 exit claim:** clean wallet trade episodes and estimated closed outcomes are reproducible from point-in-time D1 evidence, while uncertain histories remain explicitly unresolved. D3 wallet profile construction is next.