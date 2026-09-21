# G1C V2 Quote-Valuation Review Production Presence — Design

**Date:** 2026-09-21  
**Status:** read-only production presence proof only; no automatic review execution

## Purpose

The offline multi-reference quote-valuation review is implemented and tested separately.

Trusted production use must prove that the exact active immutable release physically contains the review CLI and module before a trusted administrator points it at protected quote-reference artifacts.

This slice adds presence/provenance proof only.

## Production verifier contract

The verifier requires:

- release-local console script `shreks-g1c-v2-quote-valuation-review`;
- regular non-symlink executable script;
- resolved script path exactly under the expected active immutable release;
- Python module `shreks_brain.g1c_v2_quote_valuation_review`;
- module path resolved inside that same expected release.

Expected evidence:

```text
g1c_v2_quote_valuation_review=present
g1c_v2_quote_valuation_review_path=<exact-release-local-path>
g1c_v2_quote_valuation_review_module=<exact-release-local-module-path>
```

The production verifier must not execute the review CLI.

## Runbook contract

The release runbook documents a trusted-admin review command over explicit existing quote-reference file paths.

There are no reference-selection defaults.

The review remains:

`REVIEW_EVIDENCE_ONLY`

under:

`median_exact_reference_values`

The runbook states that the review does not authorize production candidate values and must not trigger candidate authority.

## Authority boundary

This slice adds no:

- SQLite read;
- market-row selection;
- quote-reference capture;
- sizing-proposal execution;
- candidate-value authority;
- candidate-authority invocation;
- candidate authoring;
- transition binding;
- readiness;
- manifest rotation;
- scoring/model fitting;
- PAPER promotion;
- signing/submission;
- LIVE.

A later separate seal/deploy step is required before production use.
