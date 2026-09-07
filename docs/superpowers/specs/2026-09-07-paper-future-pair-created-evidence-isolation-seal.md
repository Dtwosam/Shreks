# PAPER Future Pair-Created Evidence Isolation — Production Seal

**Date:** 2026-09-07  
**Behavior merge:** `7dc6ceee5123f8271280260ca7d09c98a2148ab0`  
**Implementation PR:** #231

## Status

Production PAPER historical replay reproduced a deterministic campaign failure on candidate `228764`.

The persisted market row exposed:

`pair_created_at_unix_ms > observed_at_unix_ms`

The strict observer market model correctly rejects that impossible chronology. The failure was that candidate selection, canonical market replay, and aggregate regime replay could select the contradictory row before the model boundary, causing the whole PAPER campaign cycle to fail closed and restart repeatedly.

FL9 evidence population was not mutated while this reliability fault was investigated. LIVE remains disabled.

## Sealed behavior

Contradictory market rows where:

`pair_created_at_unix_ms IS NOT NULL AND pair_created_at_unix_ms > observed_at_unix_ms`

are now ineligible at the relevant read boundaries:

- observer current-market selection;
- observer same-path replay/history selection;
- pair-created fallback selection;
- PAPER recent-candidate selection;
- aggregate regime market selection.

The raw SQLite rows are preserved. No historical evidence is rewritten or deleted.

When an older valid row still satisfies the existing source, pair, freshness, and point-in-time rules, the existing deterministic fallback may use it. Otherwise the malformed evidence remains unavailable.

## RED evidence

Test-only PR head `f7e786c9b0f0eb1e7772be4b00a3e220a295bee5`.

CI run `34113264141`:

- Python: `3 failed, 3196 passed`;
- the market replay regression failed on the exact future pair-created invariant;
- the aggregate regime regression failed on the exact future pair-created invariant;
- the candidate-selection regression initially also exposed one test-only missing import;
- Rust: GREEN;
- repository safety: GREEN;
- native ARM64 release verification: GREEN.

The missing test import was corrected before final implementation verification.

## GREEN evidence

Final implementation head `2317a2fc856dc6a642b20fb92206df32e873ec08`.

PR CI run `34113433800`:

- Python: `3199 passed`;
- Rust workspace: GREEN;
- repository safety: GREEN;
- native ARM64 release verification: GREEN.

Merged-main CI run `34113691942` on behavior merge `7dc6ceee5123f8271280260ca7d09c98a2148ab0`:

- Python: GREEN;
- Rust workspace: GREEN;
- repository safety: GREEN;
- native ARM64 release verification: GREEN.

## Authority boundary

This fix adds no:

- strategy threshold change;
- safety-veto weakening;
- scoring/risk/sizing change;
- execution assumption change;
- PAPER promotion authority;
- model training or self-promotion;
- wallet/signing authority;
- transaction submission;
- LIVE enablement.

## Production next gate

Release and deploy this exact sealed behavior, then prove on the VPS that:

1. `shreks-paper-campaign.service` recovers through normal systemd preflight;
2. campaign checkpoints advance without the candidate-228764 chronology crash;
3. observer and paper-evidence services remain healthy;
4. the previously identified FL9 sessions 55–61 remain unchanged until core PAPER health is restored.

LIVE remains disabled.
