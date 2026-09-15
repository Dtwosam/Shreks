# FL9 V2 First-Champion — Bounded Future-Path Loading Seal

**Date:** 2026-09-15  
**Status:** SEAL PR PENDING; IMPLEMENTATION MAIN GREEN; PRODUCTION RETRY NOT YET AUTHORIZED

## Purpose

Bind the verified FL9 V2 first-champion future-path memory correction to a release-authorized seal commit without changing runtime implementation, model policy, evaluation policy, economics policy, PAPER promotion state, or LIVE state.

## Production failure evidence

The first authorized V2 first-champion evidence attempt ran from release:

`6d552932ba24239bde16b19dbb677c881b8ba25b`

under transient unit:

`shreks-fl9-v2-champion-20260915T121508Z.service`

The preflight safety gates passed before scoring:

- request reauthentication: PASS;
- full PAPER quiescence: PASS;
- database holder gate: PASS.

The process was later killed by the global OOM killer before any final or staging V2 evidence path was published. Kernel evidence recorded the V2 process at approximately 11.7 GB anonymous RSS immediately before kill. The wrapper restored the normal PAPER services after the terminal failure.

The failed attempt therefore remains physical evidence only. It produced no finalized V2 champion evidence and authorizes no promotion.

## Root cause

The V2 bundle path used the generic future-path training-label loader. That loader materialized the complete label-v1 source population in Python before the V2 bundle selected the frozen accepted cohort.

The production source contained approximately 2.04 million label-v1 rows, while the frozen V2 cohort contains 274,334 accepted decision identities. Materializing the full label population caused the observed memory exhaustion before champion evidence construction could complete.

## Corrective implementation

Implementation PR #299, `fix: bound FL9 V2 future-path loading`, replaced only the V2 future-path read path.

The correction:

- adds a cohort-scoped future-path SQLite reader;
- loads the authenticated accepted decision identities into a TEMP `WITHOUT ROWID` table;
- joins the physical future-path source to those identities with fixed horizon and label version before rows enter Python;
- streams the query cursor and does not use `.fetchall()` in the bounded loader;
- preserves canonical FastEvent source validation and conflict handling;
- preserves deterministic ordering and logical fingerprinting;
- rejects duplicate requested identities;
- fails closed when the returned target population does not exactly match the requested cohort population;
- changes only the FL9 V2 bundle to use the bounded reader.

No storage migration is required. The existing `fast_future_path_labels` primary key supports indexed decision/horizon/version lookup.

## Verification evidence

PR #299 final head:

`23bcfbf63449ba90900a0719743637d9efdb398d`

PR CI run:

`34976619534`

All four required PR gates passed:

- Repository safety;
- Python tests (`3385 passed`);
- Rust tests;
- ARM64 release build.

Squash-merged implementation main:

`dd6645cd98d177dae7eb967125d2039b03f4c632`

Exact merged-main CI:

`34983864170`

All four canonical main gates passed again:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

The automatic release workflow for `dd6645cd98d177dae7eb967125d2039b03f4c632` correctly skipped because that implementation commit is not a `seal:` commit. This is the repository's intended release gate.

## Immutable release authorization

After this documentation-only seal PR lands on `main` with a subject beginning `seal:`, the repository release workflow may build a new immutable ARM64 release for that exact sealed SHA, but only after exact sealed-main CI passes successfully.

This seal introduces no runtime implementation change beyond the already verified `dd6645cd98d177dae7eb967125d2039b03f4c632` implementation tree plus this documentary binding.

The currently deployed release remains immutable and must not be patched in place.

## Retry boundary

The failed first-champion attempt must not be retried from the old release or by reusing the old host request as though it were bound to the new release.

The preserved request:

`v2-first-champion-request.json`

has request fingerprint:

`23c5782ab0f35310f5c687a4552806c0547dcf2448dfd1f084d8ed235b7fb7ed`

and is explicitly bound to release source SHA:

`6d552932ba24239bde16b19dbb677c881b8ba25b`

A new sealed release therefore requires a fresh canonical request preparation step that binds the new release identity. Before any new scoring attempt, every proof-workspace, cohort, hydration, economics, execution-cost, and request binding must pass the current sealed code's fail-closed validation. Any source whose release-identity contract no longer matches must be regenerated only through its canonical repository-controlled path.

The next production sequence is strictly:

1. merge this seal PR with a `seal:` subject;
2. exact sealed-main CI passes all four canonical gates;
3. automatic immutable ARM64 release for the exact sealed SHA completes and its release assets verify;
4. protected deployment installs that exact release;
5. production verification proves `/opt/shreks/current`, release manifest, and runtime process identity bind to the sealed SHA;
6. prepare and strictly read back a fresh V2 host request bound to the sealed release and the frozen evidence inputs;
7. confirm the V2 evidence destination is absent and no stale staging output is reused;
8. execute exactly one new authorized V2 first-champion evidence attempt under full quiescence and an empty database-holder gate;
9. restore PAPER on every terminal path;
10. inspect immutable evidence only if the runner reports success and strict readback passes.

No operational RAM/swap workaround substitutes for the bounded-reader correction.

## Promotion boundary

A successful evidence run would authorize evidence inspection only. It would not authorize automatic runtime promotion.

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
