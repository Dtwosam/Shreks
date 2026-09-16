# FL9 V2 First-Champion — Cohort-Bounded Input Materialization Seal

**Date:** 2026-09-16  
**Status:** SEAL PR PENDING; IMPLEMENTATION MAIN GREEN; PRODUCTION RETRY NOT YET AUTHORIZED

## Purpose

Bind the verified FL9 V2 first-champion cohort-bounded input/materialization correction to a release-authorized seal commit without changing runtime implementation, frozen cohort policy, model policy, evaluation policy, economics policy, PAPER promotion state, or LIVE state.

## Production failure evidence

Sealed release:

`c6473a1a8b1252ade0ad1883ab4ce2f33bf70f46`

already contained the bounded future-path SQLite correction. A later authorized V2 first-champion production scoring attempt under that release nevertheless reproduced the prior memory-exhaustion signature at approximately 11.7 GB anonymous RSS before finalized V2 evidence was published.

That failure demonstrated that bounding only the future-path SQL population was insufficient. Other production-scale Python materializations remained on the V2 scoring path.

The failed attempt remains physical failure evidence only. It produced no promotable V2 champion evidence and authorizes no PAPER or LIVE promotion.

## Corrective implementation

Implementation PR #301, `fix: bound FL9 V2 cohort input materialization`, narrows the remaining production V2 memory amplification while preserving fail-closed authentication and evidence semantics.

The correction:

- authenticates the complete proof feature JSONL while retaining only the frozen accepted-cohort feature records in Python;
- keeps proof binding anchored to the full feature-source SHA rather than incorrectly comparing a selected-cohort logical fingerprint to the full proof population;
- authenticates the complete training-economics overlay while retaining only accepted-cohort rows for the frozen 30000 ms horizon and requested label version;
- streams canonical counterfactual provenance one accepted label at a time over one read-only SQLite connection instead of materializing the full cohort lookup tuple, set, and provenance dictionary;
- releases selected-label and selected-economics containers after target projection;
- computes future-path logical fingerprints incrementally while preserving the exact legacy canonical JSON-array bytes;
- computes counterfactual-dataset logical fingerprints incrementally while preserving the exact legacy canonical JSON-array bytes;
- routes the production `shreks-fl9-v2-first-champion` CLI through the bounded host runner;
- preserves deployed release identity validation, frozen cohort validation, hydration-policy authentication, economics-manifest authentication, execution-cost policy binding, database quiescence, database change sentinel, staging, atomic publication, and strict evidence readback.

The correction does not rerun or mutate FL4. It does not alter the frozen accepted cohort, training/validation/test partitions, target definitions, evaluation policy, champion policy, or promotion policy.

## TDD and verification evidence

The branch used explicit RED/GREEN contracts for the production-scale materializations.

A provenance-lifetime RED commit:

`bb171dc27fa7d484627bc84e32bdfcf2b6a9f169`

produced CI run:

`35090559199`

with exactly the new provenance contract failing while the existing Python suite otherwise passed (`3391 passed, 1 failed`) and Rust, ARM64, and repository-safety lanes remained green.

A counterfactual-fingerprint RED commit:

`1648fcd481d44f3445fe6662489a6b2df8d2a549`

produced CI run:

`35091419944`

with exactly the new incremental-fingerprint contract failing while the existing Python suite otherwise passed (`3392 passed, 1 failed`) and the other canonical lanes remained green.

Final implementation PR head:

`afda055fdb5bcf1eebd0bbf54827758a3ed6fa47`

Exact-head PR CI:

`35093483377`

All four required gates passed:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

The final parity suite also proves that the incremental future-path and counterfactual fingerprints remain byte-identical to the legacy canonical JSON-array representation.

Squash-merged implementation main:

`11a61b87e4b67a48d65a7b2a81132a3091693f99`

Exact merged-main push CI:

`35093824781`

completed successfully for that exact SHA, with all four canonical main gates green:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

The implementation main commit is intentionally not release-authorized because its subject does not begin with `seal:`.

## Immutable release authorization

After this documentation-only seal PR lands on `main` with a subject beginning exactly `seal:`, the repository release workflow may build a new immutable ARM64 release for that exact sealed SHA, but only after exact sealed-main CI passes successfully.

This seal introduces no runtime implementation change beyond the already verified `11a61b87e4b67a48d65a7b2a81132a3091693f99` implementation tree plus this documentary binding.

The currently deployed release remains immutable and must not be patched in place.

## Evidence-input reuse boundary

The prior c647 proof/request chain must not be treated as release-bound evidence for the new sealed release.

A new sealed release requires a fresh canonical proof/request preparation path whose release-identity binding resolves to the new sealed SHA. Any proof workspace or request whose release-source contract names `c6473a1a8b1252ade0ad1883ab4ce2f33bf70f46` remains historical evidence only for that release.

Frozen non-release-bound inputs may be reused only when the current sealed code's canonical fail-closed validators authenticate them without modification. In particular, the existing economics overlay may be reused only if its complete manifest, rows, feature-source binding, future-path binding, cohort binding, quantity, and execution-cost-policy contracts all revalidate. No stale request or release-bound proof may be relabeled or edited to manufacture compatibility.

FL4 physical execution is already complete and must not be rerun for this seal.

## Production retry boundary

The next production sequence is strictly:

1. merge this seal PR with a `seal:` subject;
2. exact sealed-main CI passes all four canonical gates;
3. automatic immutable ARM64 release for the exact sealed SHA completes and release assets verify;
4. protected deployment installs that exact release;
5. production verification proves `/opt/shreks/current`, release manifest, and runtime process identity bind to the sealed SHA;
6. generate and strictly authenticate a fresh proof workspace through the canonical repository-controlled path where the release-identity contract requires it;
7. canonically prepare and strictly read back a fresh V2 host request bound to the sealed release and frozen validated inputs;
8. confirm the V2 evidence destination is absent and no stale staging output is reused;
9. execute exactly one newly authorized V2 first-champion evidence attempt under full PAPER quiescence and an empty database/WAL/SHM holder gate;
10. restore PAPER on every terminal path;
11. inspect immutable evidence only if the runner reports success and strict readback passes.

No swap, RAM expansion, direct release-directory patch, stale-request reuse, or bypass of the protected deployment path substitutes for these gates.

## Promotion boundary

A successful scoring/evidence run would authorize evidence inspection only. It would not authorize automatic runtime promotion.

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
