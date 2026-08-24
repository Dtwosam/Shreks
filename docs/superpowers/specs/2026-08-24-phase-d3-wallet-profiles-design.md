# Phase D3 Wallet Profiles Design

**Project:** Shreks  
**Phase:** D3 — Wallet profiles  
**Base:** sealed D2 head `3045062d0b36f3de49e029fa32d112ac874a141e`

## 1. Goal

Build reproducible, confidence-weighted wallet histories from D2 wallet-trade reconstructions without turning sparse or uncertain history into a trading signal.

D3 is an evidence-aggregation layer. It must answer questions such as how much usable closed history exists, what the median reconstructed outcome looks like, how long trades tend to remain open, how much of the evidence is direct versus inferred, and—when explicit versioned research context exists—what entry-quality, entry-timing, drawdown, rug-exposure, and regime behavior has been observed.

D3 does **not** decide whether a wallet is smart, rank wallets, change a setup/score/decision/risk rule, or authorize a trade.

## 2. Existing boundary

D2 already owns conservative reconstruction under `shreks_brain.wallets`:

- one `WalletTradeReconstruction` per wallet/candidate mint/as-of time,
- `CLOSED`, `OPEN`, and `UNRESOLVED` episodes,
- `DIRECT`, `MIXED`, and `INFERRED` episode evidence quality,
- estimated closed return and raw counter-asset PnL only for clean cycles,
- explicit halt when inventory continuity becomes uncertain.

D3 consumes those domain objects. It performs no provider, RPC, SQLite, wall-clock, price, FX, or token-decimal lookup.

## 3. New modules

Add two focused Python modules inside the existing wallet package:

- `python/src/shreks_brain/wallets/profile_models.py` — immutable D3 policy/context/profile domain objects and validation.
- `python/src/shreks_brain/wallets/profiles.py` — the pure deterministic profile reducer and weighting helpers.

`python/src/shreks_brain/wallets/__init__.py` re-exports the approved D3 public API beside the existing D2 symbols.

No Rust file changes in D3.

## 4. Public API

D3 adds exactly these public wallet symbols:

- `WalletEpisodeProfileContext`
- `WalletProfile`
- `WalletProfilePolicy`
- `WalletRegimeProfile`
- `build_wallet_profile`

The existing ten D2 wallet symbols remain unchanged.

## 5. Profile policy

`WalletProfilePolicy` is required; D3 ships no production weighting defaults.

Fields:

- `version: str`
- `direct_episode_weight: float`
- `mixed_episode_weight: float`
- `inferred_episode_weight: float`
- `full_confidence_effective_sample_size: float`

Weights must be finite and satisfy:

`0 <= inferred <= mixed <= direct <= 1`

`direct_episode_weight` must be positive. `full_confidence_effective_sample_size` must be finite and strictly positive.

This policy controls evidence weighting only. It is not a wallet-quality policy and contains no trading threshold.

## 6. Point-in-time contract

`build_wallet_profile` takes:

- one wallet,
- one `as_of_unix_ms`,
- one tuple of D2 `WalletTradeReconstruction` values,
- one tuple of optional `WalletEpisodeProfileContext` values,
- one explicit `WalletProfilePolicy`.

Every reconstruction must:

- belong to the requested wallet,
- have `as_of_unix_ms` exactly equal to the profile as-of time,
- represent a unique candidate mint.

Exact as-of equality prevents a profile from silently mixing stale and fresh wallet histories.

Every episode timestamp must be at or before the profile as-of time.

## 7. Closed, open, and unresolved history

Only D2 `CLOSED` episodes contribute to outcome, win-rate, hold-time, raw-PnL, and optional context-derived metrics.

`OPEN` and `UNRESOLVED` episodes remain visible through counts. They are never converted to zero-return trades and never included in closed-outcome aggregates.

A D2 reconstruction with `halted_on_uncertain_inventory=True` increments an explicit halted-reconstruction count. D3 does not reconstruct beyond the D2 halt.

## 8. Evidence weighting and sample confidence

Each closed episode receives the policy weight associated with its D2 evidence quality.

D3 records:

- direct/mixed/inferred closed counts,
- `effective_closed_sample_size = sum(closed episode weights)`,
- `evidence_sample_confidence = min(effective_closed_sample_size / full_confidence_effective_sample_size, 1.0)`.

`evidence_sample_confidence` measures only the amount/quality of evidence under the supplied policy. It is **not** win probability, expected return, wallet quality, or permission to trade.

If all available closed episodes have zero policy weight, weighted metrics remain unknown rather than becoming zero.

## 9. Core D2-derived profile metrics

Without any extra context, D3 can safely compute:

- total reconstruction and episode counts,
- closed/open/unresolved episode counts,
- halted reconstruction count,
- direct/mixed/inferred closed counts,
- effective closed sample size,
- evidence sample confidence,
- confidence-weighted median reconstructed return,
- confidence-weighted win rate using `return > 0` as win and keeping flat outcomes in the denominator,
- confidence-weighted median hold duration from `closed_at - opened_at`.

Weighted medians are deterministic: sort by metric value and stable episode identity, then choose the first value whose cumulative positive weight reaches at least half the total positive weight.

No arithmetic mean expectancy is introduced in D3.

## 10. Raw counter-asset PnL

D2 closed raw PnL may be summed only when **all** closed episodes use the same counter-asset mint.

When that is true, the profile exposes:

- `aggregate_pnl_counter_asset_mint`
- `aggregate_realized_pnl_counter_raw`

When there are no closed episodes or closed episodes use multiple counter assets, both fields are `None`.

D3 performs no SOL/USD, token/USD, FX, or decimal conversion.

## 11. Optional episode research context

D2 does not contain enough evidence to manufacture entry-quality, candidate-discovery timing, drawdown, rug exposure, or entry-regime history. D3 therefore accepts these only through explicit `WalletEpisodeProfileContext` values.

Each context contains:

- `wallet: str`
- `candidate_mint: str`
- `episode_index: int`
- `observed_at_unix_ms: int`
- `context_version: str`
- `entry_quality_pct: float | None`
- `entry_delay_from_candidate_discovery_ms: int | None`
- `max_drawdown_pct: float | None`
- `rug_exposed: bool | None`
- `regime: MarketRegime | None`

`entry_quality_pct` is a versioned research metric on `0..100`; D3 aggregates it but does not define or derive the upstream formula. The `context_version` names that upstream semantic definition, and a single profile may not mix context versions.

`entry_delay_from_candidate_discovery_ms` is the non-negative delay from the candidate's decision-safe discovery timestamp to the reconstructed entry timestamp.

`max_drawdown_pct` is a non-negative `0..100` drawdown magnitude observed for the closed episode.

`rug_exposed` is tri-state: `True`, `False`, or unknown (`None`). Unknown never becomes false.

`regime` reuses the existing `MarketRegime` enum (`HOT`, `NORMAL`, `WEAK`, `DEAD`).

## 12. Context integrity

A context is accepted only when:

- its wallet matches the requested profile wallet,
- its `(candidate_mint, episode_index)` uniquely targets an existing D2 `CLOSED` episode,
- its local `observed_at_unix_ms` is not before that episode closed,
- its local `observed_at_unix_ms` is not after the profile as-of time,
- its `context_version` matches every other context used in the same profile.

Duplicate context identity is rejected.

Contexts for OPEN/UNRESOLVED/nonexistent episodes are rejected instead of silently ignored.

## 13. Context-derived metrics

For each optional metric D3 records a raw sample count and computes a confidence-weighted aggregate using the same D2 episode evidence weights:

- entry quality sample count + weighted median entry-quality percentage,
- entry timing sample count + weighted median discovery-to-entry delay,
- drawdown sample count + weighted median maximum drawdown percentage,
- rug-exposure sample count + weighted rug-exposure rate,
- regime sample count + per-regime behavior summaries.

A missing optional field is excluded from that metric's sample count and denominator. Missing data never becomes zero.

## 14. Regime behavior

`WalletRegimeProfile` contains:

- `regime: MarketRegime`
- `closed_episode_count: int`
- `effective_sample_size: float`
- `confidence_weighted_median_return_pct: float | None`
- `confidence_weighted_win_rate: float | None`

Only contexts with known regime contribute. Returned regime summaries use deterministic enum order: `HOT`, `NORMAL`, `WEAK`, `DEAD`, omitting regimes with no evidence.

A regime summary remains descriptive evidence; it cannot enable a strategy.

## 15. `WalletProfile` output

The immutable profile records:

- wallet/as-of/policy/context versions,
- all episode/reconstruction/evidence counts,
- effective sample size and evidence sample confidence,
- weighted median return, win rate, and hold duration,
- optional same-counter raw PnL aggregate,
- metric-specific optional-context sample counts and weighted aggregates,
- deterministic regime summaries.

All finite percentage/rate/confidence fields are validated. Counts are non-negative. The profile cannot claim context metrics without matching non-zero sample counts.

## 16. Fail-closed behavior

D3 raises `ValueError` for structural contradictions including:

- wrong wallet,
- mismatched reconstruction as-of time,
- duplicate reconstruction candidate mint,
- future episode timestamps,
- duplicate context identity,
- context targeting a non-closed/missing episode,
- context before episode close,
- future context,
- mixed context versions,
- malformed policy/context/profile values.

D3 does not silently select the latest duplicate, backfill missing context, coerce unknowns to zero, convert assets, or infer a hidden wallet score.

## 17. Explicit non-goals

D3 adds no:

- provider/RPC/SQLite read path,
- historical backfill,
- wallet ranking or `smart wallet` label,
- clustering or independence heuristic (D4),
- smart-wallet feature (D5),
- score/setup/decision/risk change,
- paper execution change,
- signer, transaction construction/submission,
- live-money authority,
- profitability claim.

## 18. Verification boundary

D3 is complete only after tests prove:

- exact public API stability,
- model/policy validation,
- point-in-time coherence,
- closed/open/unresolved separation,
- evidence-quality weighting,
- deterministic weighted medians/rates,
- same-counter raw-PnL gating,
- optional-context tri-state/missing-data behavior,
- context version/chronology integrity,
- deterministic regime summaries,
- no predecessor regressions,
- exact-head CI green.

The final branch remains draft and unmerged. D4 independence/clustering heuristics are the next source-order capability.
