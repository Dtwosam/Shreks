# FL9 V2 Frozen-Cohort FL4 Backfill — Code Seal

## Status

**SEALED IMPLEMENTATION CANDIDATE.**

This seal records the corrected FL4 backfill implementation merged on `main` at:

```text
ab3f0b4ad318ff6a64eed7d09559379a2792949c
```

Implementation PR: **#280** — `Fix FL4 backfill for frozen FL9 V2 cohort`.

The exact implementation PR head:

```text
a0cfdf4946cf4e598875fe2e822c1aeb354459a6
```

passed all four required PR CI gates in run `34694166590`:

- Repository safety: PASS
- Rust tests: PASS
- Python tests: PASS
- ARM64 release build: PASS

The merged implementation commit passed all four merged-main CI gates in run `34694318454`.

LIVE remains disabled. PAPER promotion remains blocked.

## Production condition that required this correction

The active production `fast_future_path_labels` population covered only the older 146,944-decision population, while the frozen FL9 V2 cohort authority contains 274,334 later accepted decisions. Proof regeneration alone therefore cannot supply the missing FL4 labels for the frozen V2 cohort.

The frozen cohort already authenticates each accepted decision to exactly one immutable realtime coverage session. Cross-session duplicate decision identity is forbidden. Existing FL4 semantics intentionally mark a horizon incomplete when the authenticated coverage session ends before that horizon completes.

No production FL4 labels were modified during implementation, PR verification, or merged-main verification.

## Sealed correction

The implementation adds a fail-closed, cohort-scoped backfill path:

- Python authenticates the frozen V2 cohort artifact and active V2 policy before producing a request;
- the request carries the frozen cohort fingerprint, accepted-identity fingerprint, exact source-session checkpoints, exact decision identities, and the V2 horizon;
- Rust revalidates immutable source-session checkpoints against SQLite and rejects the latest mutable session;
- Rust re-derives the accepted-decision identity fingerprint using the canonical seven-field identity ordering;
- every requested decision must map to exactly one authenticated source session;
- every requested decision is reauthenticated against the canonical stored FastEvent before labeling;
- unrelated canonical events are never selected for label writes;
- the existing FL4 labeler remains the semantic authority for complete/incomplete horizon behavior;
- writes are transactional and all-or-nothing;
- reruns are idempotent and report already-existing labels instead of duplicating them;
- the observer exposes the file-based cohort population subcommand used by the authenticated Python wrapper.

No FL4 label schema, trading strategy, model policy, PAPER execution path, risk policy, signer, transaction builder, submission path, or LIVE authority is expanded.

## Verification proof

The correction was developed test-first. Regression coverage proves:

- exact cohort identities are labeled while unrelated events remain untouched;
- complete and incomplete horizons are preserved at source-session boundaries;
- rerunning the same authenticated request is idempotent;
- canonical identity drift is rejected before writes;
- source-session checkpoint drift is rejected before writes;
- the observer can consume the authenticated request file without runtime provider configuration.

Local verification on the development Mac included `git diff --check` and the focused Python backfill tests, which passed 2/2. The Mac has no Rust toolchain, so GitHub CI supplied the authoritative Rust test and native ARM64 release evidence for both the PR head and merged implementation commit.

## Authorized physical continuation

After this seal lands and the automatic immutable ARM64 release succeeds, the next physical sequence is:

1. verify the immutable `shreks-<seal-sha>` release and exact release assets;
2. deploy that exact release through the protected production-paper deployment workflow;
3. verify `/opt/shreks/current`, release manifest identity, service executable/cwd identities, service health, and zero unexpected restarts;
4. quiesce PAPER and telemetry writers before the backfill boundary and verify no unexpected SQLite/WAL/SHM holders remain;
5. authenticate the frozen V2 cohort artifact and accepted-identity fingerprint against the active V2 policy;
6. execute exactly one cohort-scoped FL4 backfill invocation through the sealed observer binary;
7. verify the report decision count, inserted/existing totals, and complete/incomplete totals against the frozen cohort authority;
8. verify no labels were created for identities outside the authenticated cohort and that rerunning is idempotent;
9. restore PAPER and telemetry on every success or failure path;
10. only then regenerate the FL9 V2 proof inputs that depend on the corrected FL4 population.

Any source-session drift, canonical identity drift, fingerprint mismatch, unexpected database writer, transaction failure, count mismatch, or release identity mismatch is a HOLD. Do not repair evidence by relabeling identities, widening the cohort, changing coverage checkpoints, or replacing incomplete FL4 semantics with inferred completeness.

## Safety boundary

This seal does **not** authorize PAPER promotion or LIVE trading. It does not authorize transaction construction, signing, or submission. It authorizes only deployment of the cohort-scoped FL4 backfill machinery, execution of the authenticated historical label repair, and continuation of the existing read-only FL9 V2 proof path under fail-closed gates.
