# G1C V2 Review-Backed Entry Sizing Production Presence — Design

**Date:** 2026-09-22  
**Status:** read-only production presence proof only; no automatic sizing execution

## Purpose

The review-backed entry-sizing bridge is implemented and tested separately.

Trusted production use must prove that the exact active immutable release physically contains the review-backed sizing CLI and module before a trusted administrator supplies the protected multi-reference quote-valuation review artifact.

This slice adds presence/provenance proof only.

## Production verifier contract

The verifier requires:

- release-local console script `shreks-g1c-v2-review-backed-entry-sizing`;
- regular non-symlink executable script;
- resolved script path exactly under the expected active immutable release;
- Python module `shreks_brain.g1c_v2_review_backed_entry_sizing`;
- module path resolved inside that same expected release.

Expected evidence:

```text
g1c_v2_review_backed_entry_sizing=present
g1c_v2_review_backed_entry_sizing_path=<exact-release-local-path>
g1c_v2_review_backed_entry_sizing_module=<exact-release-local-module-path>
```

The production verifier must not execute the review-backed sizing CLI.

## Runbook contract

The release runbook documents one trusted-admin command that accepts only explicit:

- source runtime-manifest path;
- authenticated quote-valuation review path;
- target quote decimals;
- new non-existent proposal destination.

The review-backed command must not copy the median, review fingerprint, or conservative evidence timestamp through the old explicit-reference CLI. It authenticates the review artifact directly and preserves:

`quote_evidence_authority=MULTI_REFERENCE_REVIEW`

The output remains:

`status=PROPOSAL_EVIDENCE_ONLY`

and does not authorize production candidate values.

The runbook must state that candidate authority must not be invoked from the proposal alone.

## Authority boundary

This slice adds no:

- automatic review execution;
- automatic sizing execution;
- SQLite read;
- market-row selection;
- quote-reference capture;
- quote-value approval;
- raw entry-amount approval;
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
