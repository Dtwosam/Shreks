# G1C V2 Review-Backed Entry Sizing Transactional Publish — Design

**Date:** 2026-09-23  
**Status:** evidence-publication hardening only; no candidate/runtime authority

## Problem

The review-backed sizing wrapper authenticates the quote-valuation review, delegates proposal derivation to the canonical entry-sizing implementation, and then re-reads the review to ensure it did not change.

Today the delegated implementation writes the final destination before the wrapper performs that final review-stability check.

Therefore a concurrent review mutation can produce this unsafe outcome:

1. proposal file is written;
2. wrapper detects the review changed;
3. command returns failure;
4. the failed ceremony leaves a proposal artifact behind.

The wrapper also does not prove that the source runtime manifest stayed byte-identical from the beginning of the review-backed ceremony through final evidence publication. The underlying sizing function protects its own derivation window, but the wrapper can still publish evidence after the source changes immediately after delegated derivation returns.

## Required behavior

The review-backed sizing path must become transactional.

It must:

1. resolve and stably read the source runtime manifest;
2. resolve and stably read the authenticated review;
3. derive the proposal to a private temporary destination;
4. allow the canonical underlying sizing implementation to authenticate/recheck the source during derivation;
5. re-read both source and review after the temporary proposal has been derived;
6. require both byte sequences to remain identical to their initial snapshots;
7. only then publish the final destination with the existing write-once mode-0600 writer;
8. authenticate the final written proposal by the canonical decoder;
9. remove all temporary material automatically.

If either source or review changes at any point before final publication:

- fail closed;
- do not create the requested final destination;
- grant no authority.

## Authority boundary

This change does not:

- choose or approve candidate economics;
- create candidate-value authority;
- create candidate-authoring authority;
- author or stage a runtime-manifest candidate;
- create a transition binding;
- run readiness or rotation;
- score/model-fit;
- promote PAPER;
- access wallets;
- sign/submit;
- enable LIVE.

A separate production-presence/seal step is required before the hardened implementation is available in protected production.
