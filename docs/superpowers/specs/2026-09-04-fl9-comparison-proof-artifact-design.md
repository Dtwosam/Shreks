# FL9 Learned-vs-Baseline Comparison Proof Artifact — Design

**Date:** 2026-09-04

## Status

Implementation slice after learned chronological PAPER merge
`601b00df824aa506ec746cd1e49701b4c091f8ca` (#197).

FL9 economic superiority remains **EVIDENCE PENDING** until a real non-fixture artifact reports `SUPERIOR`.
LIVE remains disabled.

## Purpose

Create one immutable authenticated proof artifact that closes the evidence chain between:

1. the sealed deterministic baseline invocation;
2. its exact eight deterministic PAPER runs;
3. one exact learned chronological PAPER run;
4. one exact FL9 superiority policy;
5. the sealed learned-vs-baseline superiority result.

This artifact records economic truth. It does not turn a `SUPERIOR` result into promotion authority.

A valid artifact may truthfully contain `SUPERIOR`, `FAILED`, or `INSUFFICIENT_EVIDENCE`.

## Artifact topology

The comparison proof is an immutable sibling directory of the baseline invocation.

It contains exactly four files:

- `learned_run.json`
- `superiority_policy.json`
- `superiority_report.json`
- `manifest.json`

The baseline campaign and invocation are referenced by authenticated fingerprints rather than copied.

## Baseline chain

The writer opens the supplied baseline invocation through the strict #195 reader.

It then opens the campaign named by that invocation through the strict #193 reader.

Required integrity:

- invocation campaign fingerprint equals campaign artifact fingerprint;
- campaign contains exactly eight runs;
- superiority policy required baseline versions equal the deterministic catalog versions exactly and in catalog order;
- campaign run evidence remains authenticated by the #193 reader.

The comparison artifact therefore cannot silently drop a weak baseline or substitute an undeclared baseline.

## Learned run

The learned run must be exact `FastPolicyRunEvidence`.

Its run fingerprint is recomputed before any artifact is staged.

It is persisted through the existing canonical run-evidence batch codec as a batch containing exactly one run.

The artifact manifest binds both:

- learned run-evidence fingerprint;
- learned single-run batch fingerprint.

## Superiority policy codec

New schema:

`shreks.fast_policy_superiority_policy` v1.

The canonical policy document contains:

- policy version;
- exact required baseline versions;
- all minimum sample requirements;
- all net expectancy/profit factor/drawdown/cost/winner concentration thresholds;
- minimum advantage over the best deterministic baseline;
- policy fingerprint.

The policy fingerprint covers the complete schema and policy material excluding only itself.

The decoder requires exact fields, canonical JSON, strict `FastPolicySuperiorityPolicy` reconstruction, and fingerprint recomputation.

Public API:

- `encode_fast_policy_superiority_policy`
- `decode_fast_policy_superiority_policy`
- `fast_policy_superiority_policy_fingerprint_sha256`

## Superiority evaluation

The writer calls the already-sealed:

`evaluate_fast_policy_superiority(learned_run, baseline_runs, policy)`.

The resulting report is persisted through the existing canonical superiority-report codec.

No special-case treatment is applied to economic outcome.

A failed threshold remains `FAILED`.
Insufficient sample remains `INSUFFICIENT_EVIDENCE`.
Only all-pass evidence becomes `SUPERIOR`.

## Manifest

Schema:

`shreks.fast_policy_comparison_artifact` v1.

The manifest binds:

### Baseline provenance

- baseline invocation directory leaf name;
- invocation fingerprint;
- request fingerprint;
- deterministic campaign artifact fingerprint;
- deterministic catalog fingerprint;
- deterministic run-batch fingerprint;
- exact baseline run count;
- deterministic event-population fingerprint.

### Learned provenance

- candidate version;
- candidate fingerprint;
- run-evidence fingerprint;
- single-run batch fingerprint;
- learned event-population fingerprint.

### Proof provenance

- superiority policy version;
- superiority policy fingerprint;
- superiority report fingerprint;
- report decision.

### Physical child identity

- learned-run file SHA-256;
- superiority-policy file SHA-256;
- superiority-report file SHA-256.

The artifact fingerprint hashes every manifest field except itself.

The baseline invocation name is restricted to one path component to prevent traversal.

## Writer

The destination:

- must not exist;
- must be a sibling of the baseline invocation.

The writer:

1. authenticates the learned run;
2. authenticates baseline invocation + campaign;
3. requires exact catalog/policy baseline coverage;
4. evaluates superiority;
5. encodes the learned run, policy, and report canonically;
6. writes them to a private staging directory;
7. writes the authenticated manifest;
8. reads the staged artifact through the strict reader;
9. atomically renames staging to destination.

Any failure removes staging and publishes no partial artifact.

## Reader

The strict reader requires:

1. exact four-entry root;
2. canonical authenticated manifest;
3. all child file SHA-256 matches;
4. learned run batch fingerprint match;
5. exactly one learned run;
6. learned run fingerprint recomputation;
7. policy document fingerprint match;
8. policy strict decode/recomputation;
9. report strict decode/fingerprint verification;
10. baseline invocation strict read;
11. deterministic campaign strict read;
12. exact catalog/policy baseline coverage;
13. exact manifest-to-child/baseline bindings;
14. full superiority evaluator recomputation.

The persisted report must equal the newly recomputed report exactly.

This makes the artifact an executable proof record rather than a trusted summary.

## Architecture firewall

The pre-existing deterministic chronological-campaign firewall remains scoped to deterministic orchestration modules.

The new `proof_artifact.py` is intentionally a distinct evidence/proof layer and is excluded from that driver-only firewall.

The proof artifact itself may call the sealed superiority evaluator, but may not contain:

- provider/network access;
- SQLite access;
- promotion;
- signing/submission;
- LIVE authority.

## TDD provenance

Intentional RED:

`c95e5e4d2ce5ef8a483acdc5f3483b1cd51af451`.

RED CI `33885254498`:
- Rust GREEN;
- ARM64 GREEN;
- Repository safety GREEN;
- Python RED only because the new proof APIs did not yet exist.

Implementation CI later exposed one architecture-test scope mismatch: the old driver firewall scanned the newly-added proof module. The test was narrowed to preserve the original driver boundary while the new proof module carries its own stricter authority firewall.

Fixture tests prove plumbing and authentication only. Their `SUPERIOR` result is deliberately permissive synthetic evidence and is not economic proof.

## Following slice

Add one canonical file-backed proof request/orchestrator that:

1. references an authenticated deterministic campaign invocation;
2. supplies the learned campaign runtime inputs and exact learned candidate/policy configuration;
3. runs #197 learned chronological PAPER on the same immutable comparison population;
4. writes this #198 proof artifact.

That is the final repository-side seam before a real non-fixture FL9 evidence execution.

Do not start FL10 until real FL9 evidence returns `SUPERIOR`.
