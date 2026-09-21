# G1C V2 PAPER Manifest Manager Installation Proof — Release Seal

**Date:** 2026-09-21  
**Implementation main SHA:** `75dd06dca2bfc149acff950ee218b8706758cc6c`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF READ-ONLY INSTALLATION-PROOF CODE; TRUSTED-ADMINISTRATOR PROOF USE AUTHORIZED AFTER DEPLOY VERIFY; AUTOMATIC HELPER INSTALL DISABLED; PRODUCTION V2 MANIFEST ROTATION NOT AUTHORIZED; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the read-only before/after proof tool for the already-sealed release-bound PAPER manifest manager installer.

The proof tool exists to prove that one trusted-administrator helper installation did only what the installer is allowed to do:

- publish the exact sealed manager helper at the fixed root-owned destination; or
- report exact idempotent presence;

while independently proving that:

- the active immutable release did not drift;
- the protected PAPER campaign manifest did not change;
- the deployment sudoers boundary did not widen;
- the three protected PAPER runtime services did not restart or change process identity during the installation window.

This seal does not add installation authority beyond the previously sealed installer.

This seal does not authorize manifest rotation.

## Production state before this seal

The currently sealed production release is:

`c86f7f0898f4f1c641e68357998bce9649e7ebea`

Its immutable release/deploy chain completed successfully.

Production verification showed:

- current release equals the expected sealed SHA;
- observer active/running;
- PAPER evidence service active/running;
- PAPER campaign service active/running;
- zero unexpected restarts;
- protected FL9 discovery completed read-only;
- FL9 status remains `HOLD_NO_COMPATIBLE`.

The installation-proof implementation merge:

`75dd06dca2bfc149acff950ee218b8706758cc6c`

was intentionally a `feat:` commit.

Its automatic release and deploy workflow invocations were correctly skipped.

Therefore the production host does not yet contain the new proof CLI merely because the implementation landed on `main`.

## Proof implementation

The implementation adds the release-local console script:

```text
shreks-g1c-v2-paper-manifest-manager-install-proof
```

implemented by:

```text
shreks_brain.g1c_v2_paper_manifest_manager_installation_proof
```

The CLI exposes exactly two proof phases:

```text
prepare <expected-release-sha>
verify <expected-release-sha> <preinstall-snapshot> <installer-receipt>
```

The proof tool requires effective uid 0 because it reads protected root-owned host evidence.

It does not gain helper-publication authority.

It does not invoke the installer.

It does not invoke the manifest manager.

## Process-execution boundary

The proof tool has one allowlisted subprocess family:

```text
systemctl show <allowed-unit> --property=... --no-pager
```

Allowed units are exactly:

- `shreks-observe.service`;
- `shreks-paper-evidence.service`;
- `shreks-paper-campaign.service`.

The tool contains no service mutation command.

It contains no:

- `systemctl stop`;
- `systemctl start`;
- `systemctl restart`;
- reload;
- enable;
- disable;
- process kill;
- manifest replacement;
- file publication;
- scoring;
- fitting;
- promotion;
- signing;
- transaction submission;
- LIVE runtime authority.

## Exact current-release proof

Both proof phases re-authenticate the exact current immutable release.

The tool requires:

- `/opt/shreks/current` remains a valid managed symlink;
- the resolved release directory basename equals the explicit expected SHA;
- the proof CLI executes from that exact release virtualenv;
- the current canonical `RELEASE_MANIFEST.json` source SHA equals the expected SHA;
- the release manifest contains exactly one Shreks wheel record;
- the wheel is a regular non-symlink file;
- wheel size equals the release-manifest record;
- wheel SHA-256 equals the release-manifest record;
- the wheel contains exactly one sealed PAPER manifest manager member;
- the manager bytes have the exact expected executable shape.

Therefore the proof cannot silently switch to a different release or unverified wheel.

## Prepare phase

Before the trusted administrator invokes the already-sealed installer, the proof tool captures one canonical pre-install snapshot.

The snapshot records:

- release source SHA;
- resolved immutable release directory;
- Shreks wheel relative path;
- wheel SHA-256;
- sealed manager SHA-256;
- protected campaign-manifest path, SHA-256, byte size, uid, gid, and mode;
- deployment sudoers path, SHA-256, byte size, uid, gid, and mode;
- service lifecycle state for the three protected PAPER runtime services;
- a self-fingerprint;
- explicit non-authority fields.

The protected campaign manifest must be an existing regular non-symlink file with exact mode `0640`.

The deployment sudoers file must be:

- regular;
- non-symlink;
- uid 0;
- gid 0;
- mode `0440`.

Its effective non-comment content must be exactly the existing release-manager deployment rule:

```text
shreks-deploy ALL=(root) NOPASSWD: /usr/local/sbin/shreks-release-manager install /var/tmp/shreks-release-*.tar.gz /var/tmp/shreks-release-*.tar.gz.sha256 /var/tmp/shreks-release-*.RELEASE_MANIFEST.json
```

Any sudoers widening fails the proof boundary.

## Service-lifecycle snapshot

For each protected runtime service, the prepare phase records:

- ActiveState;
- SubState;
- NRestarts;
- MainPID;
- ExecMainStatus;
- ActiveEnterTimestampMonotonic.

Each service must be active/running with:

- positive MainPID;
- zero ExecMainStatus;
- valid non-negative restart count;
- positive active-enter monotonic timestamp.

The proof does not change any of these fields.

## Installer action remains separate

Between prepare and verify, the trusted administrator may invoke only the already-sealed installer:

```text
<current-release>/.venv/bin/shreks-g1c-v2-paper-manifest-manager-install <current-release-sha>
```

That installer authority was sealed separately.

This proof seal does not widen it.

The administrator must preserve the installer's canonical stdout receipt.

The proof tool does not wrap the installer and does not call it internally.

## Verify phase

The verify phase requires:

- canonical pre-install snapshot;
- valid pre-install snapshot fingerprint;
- canonical installer receipt;
- receipt status `INSTALLED` or `ALREADY_INSTALLED`;
- receipt release identity equals the active sealed release;
- receipt wheel identity equals the active release manifest;
- receipt manager digest equals the exact sealed manager member;
- receipt destination equals the fixed manager destination;
- receipt destination uid/gid/mode equal root:root 0755;
- receipt authority fields remain narrow.

It independently re-reads:

```text
/usr/local/sbin/shreks-paper-manifest-manager
```

with no-follow semantics.

The destination must be:

- regular;
- non-symlink;
- exact sealed bytes;
- uid 0;
- gid 0;
- mode `0755`.

## Protected-state invariants

The verify phase re-captures the protected campaign manifest and requires exact equality to the prepare snapshot.

That equality covers:

- path;
- SHA-256;
- size;
- uid;
- gid;
- mode.

Therefore helper installation proof fails if the protected campaign manifest changes at all during the ceremony.

The verify phase also re-captures the deployment sudoers file and requires exact equality to the prepare snapshot.

Therefore helper installation proof fails if the deploy account gains any new authority during the ceremony.

## Service-lifecycle invariants

The verify phase re-captures all three service observations.

Each observation must exactly equal its prepare-phase value.

Therefore the proof fails if any protected runtime service:

- restarts;
- changes PID;
- changes ActiveState/SubState;
- changes ExecMainStatus;
- changes ActiveEnterTimestampMonotonic;
- changes restart count.

This is stronger than merely checking that services are healthy after installation.

It proves that the helper-install ceremony itself did not touch the protected runtime lifecycle.

## Successful proof receipt

A successful verify emits canonical JSON with:

- `status = VERIFIED`;
- exact release/wheel/manager identity;
- installed destination identity;
- destination uid/gid/mode;
- pre-install snapshot fingerprint;
- installer-receipt SHA-256;
- protected campaign SHA-256;
- `campaign_manifest_unchanged = true`;
- deployment sudoers SHA-256;
- `deploy_sudoers_unchanged = true`;
- `service_lifecycle_unchanged = true`;
- proof fingerprint.

Authority remains:

- `installation_authority = PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY`;
- `manifest_rotation_authority = NOT_GRANTED`;
- `scoring_authority = NOT_GRANTED`;
- `paper_promotion_authority = BLOCKED`;
- `live_authority = DISABLED`.

## Implementation proof

Implementation PR:

`#349 — G1C: prove release-bound PAPER manager installation`

Final implementation branch head:

`23fe8c920f1f0a13259896dafcd166419dc52908`

Exact repaired branch CI:

`35596685776`

Result:

- Python: 3537 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

The two warnings are the existing intentional duplicate-ZIP-member warnings in negative transport tests.

Squash-merged implementation main:

`75dd06dca2bfc149acff950ee218b8706758cc6c`

Exact merged-main CI:

`35596934769`

Result:

- Python: 3537 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

The implementation merge correctly triggered no immutable release because its subject was `feat:`.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain to:

1. build the exact immutable ARM64 release;
2. include the read-only proof CLI in the release-local Python environment;
3. include the already-sealed installer and manager content already present in the source tree;
4. verify the release bundle;
5. create the immutable GitHub release;
6. deploy it through the existing release manager;
7. activate the ordinary protected PAPER runtime;
8. verify runtime service health and release/process provenance;
9. perform protected FL9 read-only discovery.

Automatic deployment must not run:

- proof `prepare`;
- the helper installer;
- proof `verify`;
- the manifest manager;
- any manifest rotation.

## Trusted-administrator proof authority granted by this seal

Only after the exact sealed release is active and the normal production verifier succeeds, a trusted administrator is authorized to use the release-local proof CLI around the separately authorized helper-install ceremony.

The sequence is:

```text
proof prepare
  -> separately sealed installer
  -> proof verify
```

The proof evidence should be stored in a root-private directory.

The exact current release SHA must be resolved once and passed explicitly to all three commands.

A failed prepare, failed installer, or failed verify stops the ceremony.

A failed verify is not permission to retry by mutating protected runtime state.

## No automatic helper install

This seal does not add the installer or manifest manager to GitHub deployment.

The `shreks-deploy` sudoers rule remains exactly unchanged.

No automatic workflow receives authority for:

```text
/usr/local/sbin/shreks-paper-manifest-manager
```

No automatic workflow receives authority to invoke the release-local installer.

## Production manifest-rotation boundary

Even after a successful `VERIFIED` helper-install proof, production v2 runtime-manifest rotation remains a later separate authority slice.

The proof receipt itself grants:

`manifest_rotation_authority = NOT_GRANTED`

A future rotation action must separately bind:

- exact active v1 source manifest;
- exact canonical v2 candidate;
- exact transition binding;
- explicit binding fingerprint;
- exact active release SHA;
- exact installed helper identity;
- G7 state;
- campaign-only maintenance window;
- rollback-evidence location.

This seal does not supply or invoke any of those rotation inputs.

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

A future `FOUND_COMPATIBLE` result remains insufficient by itself to authorize scoring or rotation.

## Expected production result

The automatic chain for this seal must demonstrate:

```text
seal merge
  -> exact sealed-main CI
  -> immutable release
  -> protected PAPER deploy
  -> runtime health/process provenance
  -> protected FL9 read-only discovery
```

The expected production result is a current release that contains the proof CLI.

The helper destination must not be created or changed by that automatic chain.

Only after production verification succeeds may the separate trusted-administrator proof/install/proof ceremony be attempted.

## Promotion boundary

`G1C_V2_PAPER_MANIFEST_MANAGER_INSTALL_PROOF=SEALED_READ_ONLY`

`AUTOMATIC_HELPER_INSTALL=DISABLED`

`TRUSTED_ADMIN_PROOF_USE=AUTHORIZED_AFTER_DEPLOY_VERIFY`

`TRUSTED_ADMIN_EXACT_HELPER_INSTALL=PREVIOUSLY_AUTHORIZED`

`DIVERGENT_HELPER_REPLACEMENT=NOT_AUTHORIZED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
