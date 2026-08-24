# Phase D3 Wallet Profiles Verification Record

**Base:** sealed D2 head `3045062d0b36f3de49e029fa32d112ac874a141e`.

**Design:** `docs/superpowers/specs/2026-08-24-phase-d3-wallet-profiles-design.md`.

## Implemented scope

D3 adds only deterministic, confidence-weighted wallet-history aggregation in Python:

- immutable `WalletProfilePolicy`, `WalletEpisodeProfileContext`, `WalletRegimeProfile`, and `WalletProfile` models,
- exact D3 public API extension while preserving the sealed D2 ten-symbol prefix,
- exact profile/reconstruction as-of matching and future-evidence rejection,
- CLOSED-only outcome, win-rate, hold-time, raw-PnL, and optional context aggregation,
- explicit OPEN, UNRESOLVED, and halted-reconstruction counts,
- DIRECT/MIXED/INFERRED evidence weighting through caller-supplied versioned policy,
- effective closed sample size plus bounded evidence-sample confidence,
- deterministic weighted median return, win rate, and hold duration,
- raw PnL aggregation only when every closed episode uses one counter asset,
- optional versioned entry-quality, entry-delay, drawdown, rug-exposure, and market-regime context,
- tri-state/missing context preservation and fixed HOT/NORMAL/WEAK/DEAD regime summaries.

D3 performs no provider/RPC/SQLite/wall-clock/price/FX/token-decimal reads and adds no wallet ranking, smart-wallet label, clustering/independence heuristic, D5 feature, B/C trading-policy change, signer, transaction submission, or live-money authority.

## TDD evidence

### RED

The combined D3 contract was written before production code. Two fixture defects were corrected while the branch was still RED; corrected RED commit `6c1fa718a939f04032a6982a8381b4e33c8c79ff` is the accepted RED contract.

CI `32740483736` behaved exactly as intended:

- repository safety: GREEN,
- Rust tests and workspace metadata: GREEN,
- Python: RED during collection because the five D3 public symbols did not yet exist.

No predecessor implementation regression was present.

### GREEN

Commit `1af8af89951b356d94517f5d505bc343440d0634` added the D3 models, pure reducer, and five-symbol wallet API extension. CI `32741617375` proved the D3 behavior itself: 1498 Python tests passed and exactly one stale sealed-D2 public-API test failed because it still required the wallet package to contain only the original ten symbols.

Compatibility repair commit `d8c8711af2631e01e05611642cca8486a95496d7` changed only that predecessor test so it requires the exact D2 ten-symbol **prefix** and still checks D2's reconstruct signature/research-only boundary. It does not change D2 production reconstruction behavior.

CI `32741714329` is GREEN across:

- repository safety,
- Python tests (`1499 passed`),
- Rust tests,
- workspace metadata validation.

## Integrity properties proven

- a profile cannot mix reconstructions from different as-of times,
- future episode or context evidence cannot enter a historical profile,
- OPEN and UNRESOLVED history cannot be relabeled as zero-return closed trades,
- evidence confidence reflects only caller-configured evidence quantity/quality and is not win probability or wallet quality,
- zero-weight evidence remains counted but cannot manufacture weighted performance,
- deterministic weighted medians and rates use only positive evidence weight,
- mixed counter assets cannot be summed into a fake common raw PnL,
- unknown optional context never becomes zero or false,
- optional context must uniquely target an already-CLOSED episode and cannot predate its close,
- a profile cannot mix context semantic versions,
- regime summaries remain descriptive and deterministic in HOT/NORMAL/WEAK/DEAD order,
- the sealed D2 API/order is preserved as the prefix of the D3 wallet API.

## Final seal procedure

After this record and the README D3 semantics are committed atomically:

1. freeze the branch,
2. compare exact sealed D2 -> D3 diff,
3. require README additions-only,
4. require exactly the planned D3 files plus `python/tests/test_wallet_reconstruction_public_api.py` for predecessor API-compatibility maintenance,
5. confirm no Rust/D1 storage, D2 reconstruction production logic, provider, B/C trading, signer, or live-execution files changed,
6. run one fresh exact-head CI,
7. require repository safety, Python, Rust tests, and workspace metadata all GREEN,
8. put the final D3 SHA/run only in draft PR metadata,
9. leave PR draft and unmerged.

D3 completion proves descriptive, confidence-weighted wallet histories only. D4 must establish wallet independence/clustering evidence before any wallet-derived feature is allowed to influence later trading research.
