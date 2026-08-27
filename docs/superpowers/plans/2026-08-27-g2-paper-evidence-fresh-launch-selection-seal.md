# G2 production PAPER seal — Fresh Launch evidence selection alignment

Date: 2026-08-27

## Production evidence leading to this seal

The dedicated production PAPER runtime had already been corrected to select regular Fresh Launch campaign candidates by pair age and current compatible market evidence. Read-only diagnostics then exposed an independent evidence-pipeline mismatch: the Rust `shreks-paper-evidence` daemon still bounded its Helius/Jupiter probes using the generic most-recently-observed candidate set.

Because the campaign and evidence daemon could spend their two bounded slots on different mints, a campaign candidate could have current Fresh Launch market evidence but no purpose-correct holder/quote evidence. This was a concrete mechanism for `RECONSTRUCTED_QUOTES=0` to persist after the campaign selector itself was fixed.

## Corrected behavior

The PAPER evidence daemon now uses a Fresh-Launch-aware bounded candidate selector with independent constraints for:

- current market-data freshness;
- maximum pair age;
- preferred minimum pair age;
- allowed current-market source ids; and
- maximum probe-candidate count.

The selector:

- defines launch age from `pair_created_at_unix_ms`, not Shreks discovery time;
- excludes tokens already older than the configured Fresh Launch maximum from new evidence-probe slots;
- prioritizes candidates inside the preferred entry-age window;
- permits too-young candidates to consume remaining slots for bounded evidence prefetch while they mature;
- requires a current candidate-specific market snapshot inside the configured market-freshness window;
- requires that current snapshot to come from an explicitly allowed market source;
- rejects missing, malformed, contradictory, stale, or source-incompatible selection evidence rather than guessing; and
- leaves the generic `recent_candidates` API available for generic callers.

The evidence-selection clocks are intentionally separate: token age describes launch stage, while market freshness describes whether current evidence is usable.

## Operational mirrors for the current PAPER campaign

The production host will mirror the already-sealed campaign hypotheses/contracts using non-secret runtime settings:

- `SHREKS_PAPER_EVIDENCE_LOOKBACK_SECONDS=120`
- `SHREKS_PAPER_EVIDENCE_MAX_PAIR_AGE_SECONDS=1800`
- `SHREKS_PAPER_EVIDENCE_PREFERRED_MIN_PAIR_AGE_SECONDS=60`
- `SHREKS_PAPER_EVIDENCE_MARKET_SOURCES=dexscreener`
- `SHREKS_PAPER_EVIDENCE_MAX_CANDIDATES=2`

These values do not create new trading thresholds. They align which mints receive Helius/Jupiter evidence with the existing Fresh Launch and current-market contracts used by the PAPER campaign. The evidence collection cadence is unchanged by this seal.

A direct Rust parser for the Python PAPER manifest was deliberately not added here because that manifest uses canonical tagged dataclass/float/tuple encoding plus exact fingerprint validation. Adding a second cross-language manifest decoder during a production throughput correction would materially widen the change and validation surface.

## TDD and verification evidence

Refined RED CI run: `33097746550`.

The RED failure was causal: Rust rejected the new six-part Fresh Launch evidence-selection contract because production still exposed the old selector signature. Python and repository safety remained green.

Final PR head: `d6506c46e54d9ad9a04504f23c0acb5e2cb25015`.

PR GREEN CI run: `33098927143`:

- Python tests GREEN;
- Rust tests GREEN;
- repository safety GREEN;
- native ARM64 release-build verification GREEN.

Merged behavior commit: `59fa7b63ca889cd9eb06151928f60c75693351fe` via PR #62.

Merged-main GREEN CI run: `33099221887`:

- Python tests GREEN;
- Rust tests GREEN;
- repository safety GREEN;
- native ARM64 release-build verification GREEN.

Regression coverage proves:

1. in-window Fresh Launch candidates outrank too-young candidates;
2. expired candidates do not consume evidence slots;
3. too-young candidates can still receive bounded prefetch evidence when capacity remains;
4. stale current-market evidence cannot consume a probe slot;
5. a fresh snapshot from a disallowed source cannot consume a probe slot;
6. required selection settings fail closed when missing, blank, malformed, duplicated, or internally inconsistent; and
7. selected candidates still receive exact bidirectional Helius/Jupiter evidence without adding trade authority.

## Preserved safety and authority invariants

- B1 safety vetoes remain unchanged and continue to override scoring.
- Fresh Launch liquidity, flow, scoring, decision, risk, sizing, loss, drawdown, slippage, exit, and execution thresholds are unchanged.
- PAPER fill economics are unchanged.
- No hard safety veto is weakened to manufacture trades.
- No wallet, private-key, signing, transaction-submission, or live-execution authority is added.
- No strategy or learning model can self-promote to LIVE.
- Missing or uncertain critical evidence remains fail-closed.
- LIVE remains disabled.
- Profitability remains unproven until sufficient independent PAPER trades establish positive expectancy after realistic costs with acceptable drawdown and stable execution/accounting evidence.

This documentation-only commit is the production release seal for the Fresh Launch PAPER evidence-selection alignment.