# FL9 V2 FL4 Physical Runbook — Runtime Authority Amendment

## Status

**AUTHORIZED RUNBOOK AMENDMENT.**

This document supersedes only the runtime-release binding in `docs/superpowers/specs/2026-09-12-fl9-v2-fl4-physical-execution-runbook.md` after the separately sealed PAPER campaign missing-reference-price recovery.

The physical runbook currently names the prior runtime release:

`0f508e0aca5171c491def3e605b59db0c011666e`

That release is no longer the authorized runtime for the FL4 maintenance procedure because production required the bounded PAPER recovery sealed at:

`9ca080ca9b5ad01e39bbaef6c7e024acd4a78f73`

For all uses of the physical runbook after this amendment, including mandatory precondition 1 and every requirement that `/opt/shreks/current` or `RELEASE_MANIFEST.json` equal the exact authorized release, the authorized runtime SHA is therefore:

`9ca080ca9b5ad01e39bbaef6c7e024acd4a78f73`

## Evidence for the replacement binding

The replacement release is not an unsealed operational override:

- implementation PR #287 repaired only the candidate-local missing-reference-price PAPER assembly failure;
- exact merged implementation commit `c0920ee0fe65c0f4b1aff4ca4109986dcae04acd` passed all four canonical CI lanes;
- the recovery was sealed on `main` at `9ca080ca9b5ad01e39bbaef6c7e024acd4a78f73`;
- immutable release `shreks-9ca080ca9b5ad01e39bbaef6c7e024acd4a78f73` was created successfully;
- protected deployment run `34753434843` installed that exact release successfully;
- protected production PAPER verifier run `34753625322` proved the exact release and manifest SHA, all three core PAPER services active/running, `NRestarts=0` for each service, `observer_invalid_response_lines=0`, and no recent failure signatures.

The privileged historical-evidence area remains intentionally outside the deploy account's read boundary, so this amendment does not itself close the frozen-cohort or FL4 prestate gates.

## Unchanged authority

This amendment changes nothing else in the physical runbook. The following remain exactly as sealed:

- frozen cohort path and artifact fingerprint;
- accepted-identity fingerprint;
- accepted decision count `274334`;
- horizon `30000 ms`;
- frozen source sessions `115` through `122`;
- expected complete/incomplete counts `272391` / `1943`;
- root-only cohort authentication boundary;
- requirement that the SQLite-writing observer execute as `shreks`;
- pre-mutation out-of-cohort fingerprint capture;
- quiescence and holder checks;
- one first mutation plus one controlled idempotence invocation;
- exact postcondition and restoration proofs.

No FL4 mutation is authorized merely by this amendment. Before mutation, the trusted administrator must still prove that the repaired PAPER campaign advanced beyond its pre-recovery checkpoint, reauthenticate the frozen cohort, refresh the privileged read-only FL4 prestate/scope fingerprint, and satisfy every remaining physical-runbook precondition.

## Safety boundary

This amendment does not authorize PAPER promotion, model promotion, strategy/risk changes, wallet changes, transaction construction, signing, submission, or LIVE trading. LIVE remains disabled.