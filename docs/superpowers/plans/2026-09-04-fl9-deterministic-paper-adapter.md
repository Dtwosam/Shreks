# FL9 Deterministic Lifecycle PAPER Adapter — Implementation Plan

**Date:** 2026-09-04
**Base:** `612e96f4efb6f38589f98b7a2bc8a0d057e85046`

## TDD

1. Commit deterministic adapter RED tests using the canonical candidate manifest.
2. Open draft PR and record exact missing adapter API failure.
3. Introduce one private common PAPER decision view/core in `fast_campaign_paper.engine`.
4. Keep learned public runner signature unchanged and route it through the common core.
5. Add deterministic public runner deriving identity from manifest and translating lifecycle assessments.
6. Run existing learned PAPER executor tests plus new deterministic tests.
7. Run full four-gate repository CI.
8. Freeze exact GREEN head and guarded squash merge.

## Scope

Python only plus design/plan/tests unless a proof-critical cross-language issue appears.

No provider, Rust strategy evaluation, database, registry promotion, or LIVE change.

## Following work

Produce real chronological deterministic baseline PAPER evidence campaigns and compare them to the learned candidate through the sealed FL9 superiority proof.
