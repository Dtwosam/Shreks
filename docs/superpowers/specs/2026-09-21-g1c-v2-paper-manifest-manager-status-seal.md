# G1C V2 PAPER Manifest Manager Status Observability — Release Seal

**Date:** 2026-09-21  
**Implementation main SHA:** `6d5422b97cf804bb8fa129fcb5fd663bd0daa04c`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF READ-ONLY HELPER-STATUS OBSERVABILITY; AUTOMATIC STATUS EXECUTION AUTHORIZED; HELPER INSTALLATION REMAINS SEPARATE TRUSTED-ADMINISTRATOR ACTION; PRODUCTION V2 MANIFEST ROTATION NOT AUTHORIZED; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the read-only helper-status capability so ordinary production verification can report whether the fixed root manifest-manager destination is absent, exact-current-release, divergent, metadata-drifted, or unsafe.

This seal improves observability of the remaining physical administrator gate.

It does not install, replace, chmod, chown, or invoke the helper.

It does not authorize manifest rotation.

## Production state before this seal

The currently sealed production release is:

`22dd519cb9135961a0366e3c9909b87747521a80`

That release contains the sealed rotation-readiness proof and completed immutable release/deploy/production verification successfully.

The helper-status implementation merge:

`6d5422b97cf804bb8fa129fcb5fd663bd0daa04c`

was intentionally a `feat:` commit.

Its exact merged-main CI:

`35608316642`

completed with:

- Python: 3552 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Its downstream workflow records correctly skipped because the merge subject was `feat:`:

- release `35608608572`: SKIPPED;
- deploy `35608616065`: SKIPPED.

Therefore production does not yet contain or execute the helper-status CLI merely because the implementation is on `main`.

## Status implementation

The release-local CLI is:

```text
shreks-g1c-v2-paper-manifest-manager-status
```

implemented by:

```text
shreks_brain.g1c_v2_paper_manifest_manager_status
```

It takes exactly one explicit argument:

```text
<expected-release-source-sha>
```

The probe authenticates the exact current immutable release before inspecting the helper destination.

## Release authentication

The probe requires:

- the current release symlink to resolve to the explicit expected SHA;
- execution from that exact release virtualenv;
- canonical release-manifest source SHA equality;
- exactly one Shreks wheel record;
- exact wheel size equality to the release manifest;
- exact wheel SHA-256 equality to the release manifest;
- exactly one sealed PAPER manifest-manager wheel member.

Only those authenticated bytes define the expected manager identity.

## Destination inspection boundary

The fixed destination is:

```text
/usr/local/sbin/shreks-paper-manifest-manager
```

The probe uses no-follow inspection.

It never creates or replaces this path.

It never changes ownership or permissions.

It never invokes the manager.

It emits exactly one observational status:

- `ABSENT`;
- `MATCHED_CURRENT_RELEASE`;
- `PRESENT_DIFFERENT_BYTES`;
- `PRESENT_METADATA_MISMATCH`;
- `PRESENT_UNSAFE_TYPE`.

For a regular file it records:

- SHA-256;
- uid;
- gid;
- mode;
- whether bytes match the sealed manager in the current release;
- whether metadata matches root:root `0755`.

For an absent path, no destination is created.

For a symlink or other non-regular object, the object is classified without following it.

## Production verifier integration

The reusable production PAPER verifier invokes the status CLI after proving:

- exact active release;
- exact release-manifest source SHA;

and before ordinary runtime service checks.

It prints:

```text
paper_manifest_manager_status_json=<canonical-json>
paper_manifest_manager_status=<compact-status>
```

The verifier validates:

- status schema name;
- schema version;
- `observation_authority = READ_ONLY`;
- `installation_authority = NOT_EXERCISED`;
- `manifest_rotation_authority = NOT_GRANTED`;
- status value belongs to the exact observational set.

All five observational states are accepted as observations.

This is intentional.

An `ABSENT` or divergent status must not silently become automatic installation or replacement authority.

The status command itself must succeed. If release authentication or safe destination inspection cannot be established, production verification fails rather than guessing.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain to:

1. build the exact immutable ARM64 release;
2. include the helper-status CLI in the release-local Python environment;
3. verify the release bundle;
4. create the immutable GitHub release;
5. deploy it through the existing release manager;
6. activate the ordinary protected PAPER runtime;
7. invoke the release-local helper-status CLI read-only during production verification;
8. log the canonical helper-status observation;
9. verify runtime service health and release/process provenance;
10. perform protected FL9 read-only discovery.

This is observation authority only.

## Automatic actions still forbidden

Automatic deployment and verification must not:

- run helper-install proof `prepare`;
- invoke the helper installer;
- run helper-install proof `verify`;
- execute rotation-readiness proof;
- invoke the manifest manager;
- replace or repair a divergent helper;
- chmod/chown the helper destination;
- widen `shreks-deploy` sudoers;
- rotate the production campaign manifest;
- score V2;
- promote PAPER;
- access wallets or signing material;
- submit transactions;
- enable LIVE.

## Meaning of observed helper states

### ABSENT

No helper exists at the fixed destination.

This is expected if the separately authorized trusted-administrator installation ceremony has not yet occurred.

It is not an error condition for normal PAPER runtime availability.

It grants no authority to install automatically.

### MATCHED_CURRENT_RELEASE

A regular helper exists with exact sealed current-release bytes and expected root-owned `0755` metadata.

This proves current byte/metadata identity only.

It does not prove that the authorized installation ceremony occurred.

It does not substitute for the canonical successful helper-installation proof.

It does not authorize rotation.

### PRESENT_DIFFERENT_BYTES

A regular destination exists but does not match the sealed manager bytes in the active release.

Automatic replacement is forbidden.

Trusted-administrator investigation is required.

### PRESENT_METADATA_MISMATCH

Helper bytes match the sealed manager, but uid/gid/mode do not match the expected root:root `0755`.

Automatic chmod/chown is forbidden.

Trusted-administrator investigation is required.

### PRESENT_UNSAFE_TYPE

The fixed destination exists as a symlink or other non-regular object.

The verifier does not follow or repair it.

Trusted-administrator investigation is required.

## Trusted-administrator installation boundary

The previously sealed trusted-administrator ceremony remains unchanged:

```text
installation-proof prepare
  -> separately sealed exact helper installer
  -> installation-proof verify
```

A successful helper-status observation does not replace that ceremony.

Only a canonical successful `installation-proof.json` with `status = VERIFIED` proves the separately authorized installation action.

The root helper installation remains unavailable through automatic GitHub deployment.

## Readiness boundary

The already sealed rotation-readiness proof remains usable only after a successful helper-installation proof.

A helper-status result of `MATCHED_CURRENT_RELEASE` alone is insufficient.

The readiness proof still requires the canonical verified installation proof plus the exact source/candidate/binding/G7/service/preflight evidence.

## Production rotation boundary

Even after:

- `MATCHED_CURRENT_RELEASE`;
- successful helper-installation proof;
- successful `READY_EVIDENCE_ONLY` readiness proof;

production v2 runtime-manifest rotation remains a separately explicit authority decision.

This seal does not invoke or authorize:

```text
shreks-paper-manifest-manager rotate
```

## Scoring and promotion boundary

This seal does not authorize:

- V2 scoring retry;
- model fitting;
- champion publication;
- PAPER promotion;
- wallet access;
- transaction signing;
- transaction submission;
- LIVE trading.

Protected FL9 discovery remains read-only evidence.

## Expected production result

The automatic chain for this seal must demonstrate:

```text
seal merge
  -> exact sealed-main CI
  -> immutable release
  -> protected PAPER deploy
  -> read-only helper-status observation
  -> runtime health/process provenance
  -> protected FL9 read-only discovery
```

The helper-status observation will provide the first automatic, release-authenticated evidence of the current fixed helper destination.

Whatever state is observed, the automatic chain must not mutate that destination.

## Promotion boundary

`G1C_V2_PAPER_MANIFEST_MANAGER_STATUS=SEALED_READ_ONLY`

`AUTOMATIC_STATUS_EXECUTION=AUTHORIZED_READ_ONLY`

`AUTOMATIC_HELPER_INSTALL=DISABLED`

`TRUSTED_ADMIN_EXACT_HELPER_INSTALL=PREVIOUSLY_AUTHORIZED`

`INSTALLATION_PROOF_REQUIRED_FOR_ACCEPTANCE=YES`

`ROTATION_READINESS_REQUIRES_VERIFIED_INSTALLATION_PROOF=YES`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
