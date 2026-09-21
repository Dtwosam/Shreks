# G2 verified GitHub-to-VPS release delivery

This runbook bootstraps and operates the Phase G2 PAPER deployment path. GitHub is the release and deployment control plane; the dedicated Linux VPS remains the runtime. The deployment transport path never creates, copies, reads, edits, or deletes `/etc/shreks/shreks.env`, `/etc/shreks/paper-campaign.json`, or `/var/lib/shreks`; sealed runtime preflights may read protected evidence only through the explicit read-only authority described below.

**LIVE TRADING: DISABLED.**

## Trust and authority boundary

A Shreks release is identified by one exact sealed source SHA and immutable GitHub Release tag `shreks-<40-character-sha>`. The deploy workflow accepts only an existing GitHub Release, downloads its tarball, checksum, and manifest, verifies them locally with `release_bundle.py`, then transfers only those three files to the VPS.

The deploy SSH key is a deployment transport credential only. It is separate from any future trading key and must never be reused as a trading key, signing key, provider credential, or runtime secret. Trading credentials remain host-only. GitHub Environment secret population is account configuration, not repository content.

## One-time VPS bootstrap

Run these steps from a trusted administrator session on the VPS after the G1C host layout exists.

Create a dedicated unprivileged deploy account:

```sh
sudo useradd --create-home --shell /bin/bash shreks-deploy
sudo install -d -o shreks-deploy -g shreks-deploy -m 0700 /home/shreks-deploy/.ssh
```

Install the G2 verifier and release manager from the exact sealed source checkout. Both files are root-owned and are not writable by the deploy account:

```sh
sudo install -o root -g root -m 0755 deploy/release/release_bundle.py /usr/local/sbin/release_bundle.py
sudo install -o root -g root -m 0755 deploy/release/release_manager.py /usr/local/sbin/shreks-release-manager
sudo chown root:root /usr/local/sbin/release_bundle.py /usr/local/sbin/shreks-release-manager
sudo chmod 0755 /usr/local/sbin/release_bundle.py /usr/local/sbin/shreks-release-manager
```

The PAPER manifest manager is deliberately not installed by this bootstrap or by the deployment account. Existing hosts install that helper later from an exact immutable release using the dedicated release-bound procedure below.

Install the deployment public key into `/home/shreks-deploy/.ssh/authorized_keys`, owned by `shreks-deploy:shreks-deploy` with mode `0600`. The corresponding private deploy SSH key is stored only in the GitHub `production-paper` environment as `SHREKS_DEPLOY_SSH_KEY`.

Create `/etc/sudoers.d/shreks-release-manager` as root with this single deployment command shape:

```text
shreks-deploy ALL=(root) NOPASSWD: /usr/local/sbin/shreks-release-manager install /var/tmp/shreks-release-*.tar.gz /var/tmp/shreks-release-*.tar.gz.sha256 /var/tmp/shreks-release-*.RELEASE_MANIFEST.json
```

Then validate and lock the file:

```sh
sudo chown root:root /etc/sudoers.d/shreks-release-manager
sudo chmod 0440 /etc/sudoers.d/shreks-release-manager
sudo visudo -cf /etc/sudoers.d/shreks-release-manager
```

Do not grant the deploy account general passwordless sudo, an interactive root shell, direct write access to `/opt/shreks`, or access to protected runtime configuration/state.

## GitHub `production-paper` environment

Configure exactly these deployment transport secrets in the GitHub `production-paper` environment:

- `SHREKS_DEPLOY_HOST` — pinned VPS hostname.
- `SHREKS_DEPLOY_PORT` — SSH port.
- `SHREKS_DEPLOY_USER` — `shreks-deploy`.
- `SHREKS_DEPLOY_SSH_KEY` — private key matching the deploy account public key.
- `SHREKS_DEPLOY_KNOWN_HOSTS` — trusted pinned host-key line obtained out-of-band from the VPS provider or trusted administrator channel.

Do not populate runtime provider credentials, strategy/risk overrides, campaign configuration, or future trading key material in this environment. The deploy SSH key and any trading key are different credentials and must never be copied into each other's storage boundary.

## Create a release

After a `seal:` commit lands on `main`, the normal `CI` workflow runs on that exact commit. If that `main` CI completes successfully, `Build sealed Shreks release` starts automatically for `aarch64-unknown-linux-gnu` and uses the CI-tested `workflow_run.head_sha` as the release source. The automatic path still checks out that exact SHA, confirms the commit subject contains `seal`, reruns repository safety plus Rust and Python tests, builds and verifies the allowlisted bundle, refuses a duplicate tag, and creates immutable release `shreks-<sha>`.

The manual `Build sealed Shreks release` dispatch remains available for an explicit exact sealed SHA and supported native platform. It uses the same exact-SHA, seal, full-test, bundle-verification, and duplicate-tag gates. A manual/automatic race for the same SHA is fail-closed: the existing tag wins and the later attempt refuses to overwrite it.

Automatic release creation still does **not** contact the VPS or consume the `production-paper` environment itself. After that release workflow completes successfully through the canonical sealed-main `workflow_run` path, the separate `Deploy verified Shreks release` workflow now continues automatically. The trust boundary remains separate: deployment independently resolves the exact sealed SHA/tag and verifies the immutable GitHub Release before any host contact.

Release assets are exactly:

```text
shreks-release-<sha>.tar.gz
shreks-release-<sha>.tar.gz.sha256
RELEASE_MANIFEST.json
```

The top-level release payload intentionally keeps the historical G2 allowlist so an already-installed older root verifier can stage the first release that repairs deployment activation. The exact sealed deployment-control bytes for `release_bundle.py`, `release_manager.py`, and `paper_manifest_manager.py` are embedded inside the already-allowlisted Shreks wheel as:

```text
shreks_brain/_sealed_deploy_control/release_bundle.py
shreks_brain/_sealed_deploy_control/release_manager.py
shreks_brain/_sealed_deploy_control/paper_manifest_manager.py
```

The wheel itself is a manifest-hashed release payload. During release construction, `build_release.sh` opens the completed wheel and verifies those two members are byte-for-byte identical to the exact sealed checkout before the wheel enters the release bundle. This transports the one-time root control-plane repair without changing the top-level manifest schema or making old verified releases unverifiable.

### Sealed offline Fast Lane proof tools

Verified releases also transport the native offline executables required by the FL9 evidence path inside the same manifest-hashed wheel rather than expanding the historical G2 top-level payload allowlist:

```text
shreks_brain/_sealed_fast_tools/manifest.json
shreks_brain/_sealed_fast_tools/export_fast_training_features.bin
shreks_brain/_sealed_fast_tools/shreks-fast-campaign-decision.bin
shreks_brain/_sealed_fast_tools/shreks-fast-entry-authority.bin
```

The nested manifest binds the exact release source SHA, native platform, tool names, byte sizes, and SHA-256 fingerprints. Release construction verifies the completed wheel against the native binaries built from that same checkout before the wheel is admitted to the ordinary G2 bundle.

These payloads are **offline proof tools, not runtime services**. Deployment does not execute them, does not add systemd units for them, and does not grant the deploy account access to `/var/lib/shreks`. A later PAPER-only proof workflow running under the existing `shreks` service identity may materialize authenticated copies into private runtime storage. Existing modified copies fail closed rather than being silently overwritten.

This transport adds no provider credential, wallet/signing authority, promotion authority, transaction submission, or LIVE enablement.

## Deploy a release

The normal production PAPER delivery path is now:

```text
seal merge -> CI -> immutable release -> PAPER deploy -> production verify -> protected FL9 discovery
```

A successful canonical automatic `Build sealed Shreks release` run triggers `Deploy verified Shreks release`. The deploy workflow accepts that automatic path only when the upstream release run itself came from the sealed-main `workflow_run` path and completed successfully. It derives `shreks-<sha>` from the exact upstream `workflow_run.head_sha`; it never chooses a release by freshness or branch name.

Before host contact, deployment independently loads the GitHub Release through the API and requires all of the following:

- the tag exactly equals `shreks-<sha>`;
- `target_commitish` exactly equals that 40-character SHA;
- the release is neither draft nor prerelease;
- the release reports `immutable=true`;
- the asset set is exactly the tarball, checksum sidecar, and `RELEASE_MANIFEST.json`.

Only after those checks pass does the workflow download the assets, verify the bundle locally, use strict pinned host-key checking, copy the assets to `/var/tmp`, and invoke only:

```text
sudo /usr/local/sbin/shreks-release-manager install <archive> <checksum> <manifest>
```

After a successful deployment, the same workflow invokes the reusable `Verify production PAPER runtime` workflow with the exact resolved SHA. Verification retains the `production-paper` environment and existing read-only service/provenance/journal/FL9-discovery checks. A deploy failure prevents verification; a verification or discovery failure fails the delivery chain.

The `production-paper` GitHub Environment remains authoritative. If environment reviewers or branch protections are configured, those intentional gates still apply; the automatic chain does not bypass them.

Manual controls remain available as fallbacks:

- manually dispatch `Deploy verified Shreks release` with an exact existing immutable release tag;
- manually dispatch `Verify production PAPER runtime` with an exact expected release SHA and bounded journal window;
- manually deploy an earlier immutable release for rollback.

The current release manager re-verifies the bundle, stages `/opt/shreks/releases/<sha>`, constructs the release-local Python environment at its final SHA path, re-verifies stored payloads, installs systemd unit files, atomically switches `/opt/shreks/current`, starts `shreks.target`, and checks health. A repaired manager additionally stops the runtime services explicitly before switching an existing release and verifies runtime **process identity** against the activated immutable release. The two native services must execute the exact binaries inside that release, and every runtime service must have its working directory rooted at that release. If activation fails after a prior release was active, the repaired manager restores the previous verified release and its previous unit files.

## Recover or update sealed deployment control scripts

The root-owned `/usr/local/sbin` verifier and manager are intentionally outside the unprivileged deploy account's write authority. If a verified release contains a deployment-manager fix that must replace an older bootstrapped manager, perform this bounded recovery from a trusted administrator session only after verifying that `/opt/shreks/current` and its `RELEASE_MANIFEST.json` identify the intended immutable release.

The release verifier and release manager are transported inside the release's manifest-hashed wheel. Extract only those two fixed recovery members from that verified wheel into a private temporary directory, install them root-owned, then reconcile the already-selected immutable release:

```sh
set -euo pipefail
umask 077

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
CURRENT_SHA="$(basename "$CURRENT_RELEASE")"
MANIFEST_SHA="$(python3 - <<'PY'
import json
with open('/opt/shreks/current/RELEASE_MANIFEST.json') as handle:
    print(json.load(handle)['source_sha'])
PY
)"

if [[ ! "$CURRENT_SHA" =~ ^[0-9a-f]{40}$ || "$MANIFEST_SHA" != "$CURRENT_SHA" ]]; then
  echo "current release identity is not verified" >&2
  exit 2
fi

mapfile -t WHEELS < <(find "$CURRENT_RELEASE/wheelhouse" -maxdepth 1 -type f -name 'shreks_brain-*.whl' -print | sort)
if [[ "${#WHEELS[@]}" -ne 1 ]]; then
  echo "expected exactly one verified Shreks wheel" >&2
  exit 2
fi

CONTROL_TMP="$(mktemp -d)"
trap 'rm -rf "$CONTROL_TMP"' EXIT

python3 - "${WHEELS[0]}" "$CONTROL_TMP" <<'PY'
from pathlib import Path
import sys
import zipfile

wheel = Path(sys.argv[1])
out = Path(sys.argv[2])
members = {
    "release_bundle.py": "shreks_brain/_sealed_deploy_control/release_bundle.py",
    "release_manager.py": "shreks_brain/_sealed_deploy_control/release_manager.py",
}
with zipfile.ZipFile(wheel) as archive:
    for output_name, member in members.items():
        try:
            payload = archive.read(member)
        except KeyError as exc:
            raise SystemExit(f"sealed deployment-control member missing: {member}") from exc
        (out / output_name).write_bytes(payload)
PY

sudo install -o root -g root -m 0755 \
  "$CONTROL_TMP/release_bundle.py" \
  /usr/local/sbin/release_bundle.py
sudo install -o root -g root -m 0755 \
  "$CONTROL_TMP/release_manager.py" \
  /usr/local/sbin/shreks-release-manager

sudo /usr/local/sbin/shreks-release-manager activate-existing "$CURRENT_SHA"
```

`activate-existing` re-verifies the stored release before activation. Even when `/opt/shreks/current` already points to that same SHA, the repaired manager reconciles the runtime by explicitly stopping the three Shreks services, stopping `shreks.target`, reinstalling the release's unit files, reloading systemd, starting the target, checking unit health, and verifying process identity. A stale process from a previous release therefore cannot be reported as a successful activation.

This recovery updates only the root-owned deployment-control scripts and runtime activation state. It does not read or modify `/etc/shreks/shreks.env`, `/etc/shreks/paper-campaign.json`, `/var/lib/shreks`, wallet/signing material, PAPER/LIVE authority, or any trading credential. Do not widen the deploy account's sudoers rule merely to avoid this administrator boundary.

## Install the sealed PAPER manifest manager helper

Installing the root-owned PAPER manifest manager is a separate trusted-administrator maintenance action. It is not part of normal GitHub deployment, is not delegated to `shreks-deploy`, and does not authorize a runtime-manifest rotation.

Use this path only after an immutable release containing the installer is active and production verification has succeeded. Resolve the active release once, bind the command to that exact SHA, and invoke the installer from that exact release virtualenv:

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
CURRENT_SHA="$(basename "$CURRENT_RELEASE")"

if [[ ! "$CURRENT_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "current release identity is invalid" >&2
  exit 2
fi

sudo "$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-paper-manifest-manager-install" "$CURRENT_SHA"
```

The installer independently requires all of the following before it publishes anything:

- effective uid 0;
- `/opt/shreks/current` is still a symlink to the explicit expected release SHA;
- the installer itself is executing from that exact release virtualenv;
- the current release has a canonical `g2-release-manifest-v1` manifest with the same source SHA;
- the manifest contains exactly one Shreks wheel record;
- the wheel is a regular non-symlink file whose exact size and SHA-256 match the release manifest;
- the wheel contains exactly one unencrypted `shreks_brain/_sealed_deploy_control/paper_manifest_manager.py` member;
- that member has the expected manager executable shape.

Immediately before publication, the installer rechecks that `/opt/shreks/current` still identifies the same explicit release. The destination parent must be a real root-owned directory and must not be group- or world-writable.

For a first installation, the helper is published at:

```text
/usr/local/sbin/shreks-paper-manifest-manager
```

with root ownership and mode `0755`. Publication uses no-overwrite semantics. The installer does not replace a different existing helper. If the destination already contains the exact sealed bytes with exact root ownership and mode, the command is idempotent and reports `ALREADY_INSTALLED`; any byte or metadata mismatch fails closed for administrator investigation.

A successful canonical receipt binds the installation to:

- current release source SHA;
- exact manifest-hashed wheel relative path and SHA-256;
- exact sealed wheel-member path;
- installed manager SHA-256;
- destination path and metadata.

The receipt grants only exact helper installation authority. It records manifest rotation as `NOT_GRANTED`, scoring as `NOT_GRANTED`, PAPER promotion as `BLOCKED`, and LIVE as `DISABLED`.

This installer does not stop or restart any Shreks service. It does not read or modify `/etc/shreks/shreks.env`, `/etc/shreks/paper-campaign.json`, `/var/lib/shreks`, systemd units, G7 state, SQLite/E11 state, wallets, signing material, or transaction paths.

Do not add the installer or `shreks-paper-manifest-manager` to the `shreks-deploy` sudoers rule. A later production manifest rotation remains a separate explicitly authorized administrator action.

## Observe the release-bound helper status read-only

The release-local helper-status command provides read-only observability for the physical administrator gate:

```sh
CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
CURRENT_SHA="$(basename "$CURRENT_RELEASE")"

"$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-paper-manifest-manager-status" "$CURRENT_SHA"
```

It authenticates the exact current immutable release, release manifest, manifest-hashed Shreks wheel, and sealed manager member before inspecting:

`/usr/local/sbin/shreks-paper-manifest-manager`

The command never creates, replaces, chmods, chowns, or invokes the helper. It reports one of:

- `ABSENT` — no helper exists at the fixed destination;
- `MATCHED_CURRENT_RELEASE` — bytes and expected root-owned `0755` metadata match the sealed manager in the current release;
- `PRESENT_DIFFERENT_BYTES` — a regular file exists but does not match the current sealed manager bytes;
- `PRESENT_METADATA_MISMATCH` — bytes match but uid/gid/mode do not;
- `PRESENT_UNSAFE_TYPE` — the destination exists as a symlink or other non-regular object.

Normal production verification prints both the canonical status JSON and the compact status value. Absence or divergence is observational evidence and does not cause automatic installation or replacement. A status inspection failure itself fails verification because the host state could not be established safely.

Every result records observation authority as `READ_ONLY`, installation authority as `NOT_EXERCISED`, manifest rotation as `NOT_GRANTED`, scoring as `NOT_GRANTED`, PAPER promotion as `BLOCKED`, and LIVE as `DISABLED`.

After the complete production verifier succeeds, the runner extracts exactly one already-validated canonical helper-status line from its SSH transcript, revalidates the schema, exact release SHA, observational status set, and all non-authority fields locally, and writes only:

```text
status.json
status.json.sha256
```

into a GitHub Actions artifact named `paper-manifest-manager-status-<release-sha>-<run-attempt>`. The raw verifier transcript, SSH material, journal output, and protected runtime evidence are not uploaded. The SHA-256 sidecar binds the exact canonical `status.json` bytes. Artifact publication occurs only after the full production verifier succeeds, so it is durable verification evidence rather than a replacement for the root helper-installation proof.

## Prepare and verify the helper-installation proof

The release-bound installer intentionally has no service-management or protected-campaign mutation code. For a production installation, preserve an independent before/after proof around that already-authorized installer action.

Use this procedure only after a release containing the proof CLI has itself been sealed, deployed, and verified. The proof CLI requires root because it reads the protected campaign manifest and root-owned deployment sudoers, but it does not install the helper, does not invoke the manifest manager, and does not call any service lifecycle command. Its only systemd command is read-only `systemctl show`.

Create a root-private evidence directory and capture the exact pre-install state:

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
CURRENT_SHA="$(basename "$CURRENT_RELEASE")"
PROOF_DIR="/root/shreks-paper-manifest-manager-install-$CURRENT_SHA"

if [[ ! "$CURRENT_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "current release identity is invalid" >&2
  exit 2
fi

sudo install -d -o root -g root -m 0700 "$PROOF_DIR"

sudo sh -c '
  set -e
  umask 077
  exec "$1/.venv/bin/shreks-g1c-v2-paper-manifest-manager-install-proof"     prepare "$2" > "$3/installation-proof-pre.json"
' sh "$CURRENT_RELEASE" "$CURRENT_SHA" "$PROOF_DIR"
```

The pre-install snapshot is canonical JSON. It authenticates the exact current release and manifest-hashed wheel, fingerprints the sealed manager member, hashes the protected campaign manifest, requires the deployment sudoers file to contain only the sealed release-manager command, and records the three PAPER runtime services' active/sub states, restart counters, MainPIDs, exit status, and active-enter monotonic timestamps.

Run the already-sealed installer and preserve its canonical receipt:

```sh
sudo sh -c '
  set -e
  umask 077
  exec "$1/.venv/bin/shreks-g1c-v2-paper-manifest-manager-install"     "$2" > "$3/installer-receipt.json"
' sh "$CURRENT_RELEASE" "$CURRENT_SHA" "$PROOF_DIR"
```

Then verify the post-install state:

```sh
sudo sh -c '
  set -e
  umask 077
  exec "$1/.venv/bin/shreks-g1c-v2-paper-manifest-manager-install-proof"     verify "$2"     "$3/installation-proof-pre.json"     "$3/installer-receipt.json"     > "$3/installation-proof.json"
' sh "$CURRENT_RELEASE" "$CURRENT_SHA" "$PROOF_DIR"
```

The verifier fails closed unless all of the following remain true:

- `/opt/shreks/current` still identifies the exact expected immutable release;
- the canonical release manifest and manifest-hashed Shreks wheel still authenticate;
- the installer receipt is canonical and binds the same release, wheel, manager digest, destination, metadata, and narrow authority fields;
- `/usr/local/sbin/shreks-paper-manifest-manager` is a regular non-symlink file with exact sealed bytes, uid 0, gid 0, and mode `0755`;
- the protected PAPER campaign manifest is byte-for-byte and metadata-identical to the pre-install snapshot;
- `/etc/sudoers.d/shreks-release-manager` is unchanged and still contains only the exact release-manager deployment command;
- observer, PAPER evidence, and PAPER campaign service lifecycle observations are exactly unchanged.

A successful `installation-proof.json` records `PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY`. It still records manifest rotation as `NOT_GRANTED`, scoring as `NOT_GRANTED`, PAPER promotion as `BLOCKED`, and LIVE as `DISABLED`.

If the proof fails, do not treat helper installation as accepted and do not proceed to runtime-manifest rotation. Investigate the drift first.

## Prove protected PAPER manifest rotation readiness

After the root helper has been installed with a successful `installation-proof.json`, use the release-local readiness proof before requesting any separate production manifest-rotation authority.

This proof is deliberately non-mutating with respect to protected runtime state. It does not stop or start services, does not invoke `shreks-paper-manifest-manager`, and does not replace the active campaign manifest. It creates only a private temporary candidate copy for the existing PAPER preflight and removes that copy when the command exits.

Stage the exact canonical v2 candidate and exact transition binding as regular non-symlink files. Preserve the installation proof from the helper-install ceremony, then run:

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
CURRENT_SHA="$(basename "$CURRENT_RELEASE")"
BINDING_FINGERPRINT="<64-character-binding-fingerprint>"
CANDIDATE="/var/tmp/shreks-paper-candidate.json"
BINDING="/var/tmp/shreks-paper-transition-binding.json"
INSTALL_PROOF="/root/shreks-paper-manifest-manager-install-$CURRENT_SHA/installation-proof.json"
READINESS_DIR="/root/shreks-paper-manifest-rotation-readiness-$CURRENT_SHA"

if [[ ! "$CURRENT_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "current release identity is invalid" >&2
  exit 2
fi

sudo install -d -o root -g root -m 0700 "$READINESS_DIR"

sudo sh -c '
  set -e
  umask 077
  exec "$1/.venv/bin/shreks-g1c-v2-paper-manifest-rotation-readiness"     "$2" "$3" "$4" "$5" "$6"     > "$7/rotation-readiness.json"
' sh   "$CURRENT_RELEASE"   "$CANDIDATE"   "$BINDING"   "$INSTALL_PROOF"   "$BINDING_FINGERPRINT"   "$CURRENT_SHA"   "$READINESS_DIR"
```

The readiness proof fails closed unless all of the following are true:

- the current immutable release and manifest-hashed Shreks wheel authenticate to the explicit release SHA;
- the installed `/usr/local/sbin/shreks-paper-manifest-manager` bytes and root-owned `0755` metadata exactly match the sealed manager member in that release;
- the supplied helper `installation-proof.json` is canonical, fingerprint-valid, `VERIFIED`, and bound to the same release, wheel, manager, destination, and narrow authority fields;
- `/etc/sudoers.d/shreks-release-manager` still has the same exact narrow release-manager rule and SHA-256 recorded by the installation proof;
- `/etc/shreks/shreks.env` still binds the protected DB, E11, campaign-manifest, and G7 paths expected by the rotation manager;
- the active source manifest is canonical v1 with mode `0640`;
- the staged candidate is canonical v2;
- the exact transition-binding fingerprint equals the explicit operator value and all source/candidate identities match the binding;
- G7 operator-control state is valid and stable during the proof;
- observer, PAPER evidence, and PAPER campaign services are healthy and do not change lifecycle identity during the proof;
- the exact authenticated candidate bytes pass the existing PAPER runtime preflight from a private temporary copy;
- release/helper/sudoers/env/source/candidate/binding/G7/service observations remain stable through the end of the proof.

A successful `rotation-readiness.json` has:

```text
status=READY_EVIDENCE_ONLY
candidate_preflight_status=PASSED
runtime_env_contract=MATCHED
service_lifecycle_unchanged=true
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

`READY_EVIDENCE_ONLY` does not authorize rotation. It is evidence for a later, separately explicit production-rotation authority decision. The rotation manager independently rechecks the source, candidate, binding fingerprint, active release, runtime environment, and G7 state at invocation time.

## Manual protected PAPER manifest rotation

A runtime-manifest v2 candidate is not installed by the normal GitHub deploy chain. The deployment account keeps exactly the release-install sudo rule above and receives no passwordless authority for `shreks-paper-manifest-manager`.

After an exact sealed release containing the manifest manager is active, a trusted administrator may explicitly authorize one protected PAPER rotation. The candidate and transition binding must already have been created by the sealed G1C v2 authoring/binding path. Record the exact binding fingerprint and exact current release SHA before invoking the manager.

Stage the two immutable inputs as regular non-symlink files, then run:

```sh
sudo /usr/local/sbin/shreks-paper-manifest-manager rotate \
  /var/tmp/shreks-paper-candidate.json \
  /var/tmp/shreks-paper-transition-binding.json \
  <64-character-binding-fingerprint> \
  <40-character-current-release-sha>
```

The manager independently requires the current protected v1 manifest bytes and fingerprint to match the binding, requires the candidate v2 bytes and fingerprint to match the binding, verifies the explicit binding fingerprint and current release identity, and requires the configured production DB/E11/manifest/G7 paths in `/etc/shreks/shreks.env` to match the protected paths it will use.

The manager then:

1. stops only `shreks-paper-campaign.service`, leaving observer and paper-evidence collection running;
2. creates private `0700` rollback evidence under `/var/lib/shreks/manifest-rotations/<binding-fingerprint>/`;
3. copies the exact authenticated source manifest, candidate manifest, and transition binding into that evidence directory with mode `0600`;
4. preflights that private candidate copy against the real operational SQLite database, E11 ledger, and G7 operator-control state without executing a PAPER cycle;
5. atomically replaces only `/etc/shreks/paper-campaign.json`, preserving the source file's owner, group, and `0640` mode;
6. preflights the protected active path again before startup;
7. starts the campaign through its ordinary systemd unit so all existing `ExecStartPre` gates still run;
8. requires the campaign service to be active and its process identity to come from the exact expected immutable release;
9. writes an immutable activation receipt.

If any candidate preflight, replacement, startup, health, identity, or byte-verification step fails after campaign quiesce, the manager restores the exact source manifest, preflights it, starts the source campaign again, verifies source bytes and process health, and writes a rollback receipt when the evidence directory exists. It does not delete any candidate-run checkpoint or E11 rows that may already have been written; preserving evidence is safer than fabricating rollback history.

This command is manifest rotation authority only. It does not modify the SQLite database, E11 evidence, G7 control state, scoring evidence, champion state, wallet/signing material, transaction submission paths, PAPER promotion state, or LIVE authority. The rotation receipt records scoring authority as `NOT_GRANTED`, PAPER promotion as `BLOCKED`, and LIVE as `DISABLED`.

Do not add this manager to `/etc/sudoers.d/shreks-release-manager` and do not expose it through the automatic GitHub deployment workflow. Runtime-manifest rotation remains an explicit administrator maintenance action.

## Provenance and health checks

After deployment, verify the active immutable release identity and manifest on the VPS:

```sh
readlink -f /opt/shreks/current
cat /opt/shreks/current/RELEASE_MANIFEST.json
sudo systemctl is-active shreks.target
sudo systemctl status shreks-observe.service --no-pager
sudo systemctl status shreks-paper-evidence.service --no-pager
sudo systemctl status shreks-paper-campaign.service --no-pager
```

The resolved `current` path must end in the same 40-character SHA recorded in `RELEASE_MANIFEST.json`. For repaired production activation, process identity must also match that release: the observer and paper-evidence executables must resolve to the exact native binaries under `/opt/shreks/releases/<sha>/target/release/`, and all runtime service working directories must resolve to `/opt/shreks/releases/<sha>`.

The protected paths `/etc/shreks/shreks.env`, `/etc/shreks/paper-campaign.json`, and `/var/lib/shreks` remain outside release activation and rollback.

### Protected FL9 read-only discovery without an administrator shell

For sealed releases that contain the protected pre-deploy FL9 bridge, the automatic deployment path stages one canonical release-bound discovery request immediately before release activation:

```text
/var/tmp/shreks-fl9-v2-discovery.<request-id>.request
/dev/shm/shreks-fl9-v2-discovery.<request-id>.result.d
```

Both paths are created as the unprivileged `shreks-deploy` account. The request is mode `0644`, the result exchange is mode `0733`, and the request contains only the fixed discovery schema, bounded request ID, exact expected sealed release SHA, and creation timestamp. It contains no arbitrary command, protected path, policy value, credential, wallet material, or trading instruction.

During activation, the release-managed `shreks-paper-campaign.service` invokes exactly one startup-only privileged helper before its ordinary campaign preflight:

```text
ExecStartPre=-+/opt/shreks/current/.venv/bin/python -m shreks_brain.telemetry.fl9_v2_predeploy_discovery
```

That helper is release-local. It uses the already-authenticated FL9 discovery code to read the protected frozen cohort, preserved V2 request/hydration authority, active PAPER runtime manifest, and verified historical backup manifests. It does not write telemetry receipts while privileged and does not mutate protected evidence.

After the terminal discovery result is constructed in memory, the helper permanently clears supplementary groups and drops to the existing `shreks` UID/GID before publishing `result.json` into the deploy-owned result exchange. The existing verifier still requires the published result file to be a real mode-`0644` file owned by `shreks`, stable across no-follow reads, canonical JSON, and exactly bound to the request ID and expected/observed release SHA. A root-owned result is not trusted.

The leading `-` on the helper command keeps read-only discovery failure isolated from PAPER availability. Missing, malformed, or untrusted discovery output therefore fails production verification rather than preventing the PAPER campaign from starting.

After activation, deployment removes only its `/var/tmp` request and passes the exact request ID into the reusable `Verify production PAPER runtime` workflow. The verifier reuses the already-created `/dev/shm` exchange, performs the ordinary release/service/restart/journal checks, validates the result, and cleans up that exact exchange.

Manual verifier dispatch without a pre-staged request ID retains the prior telemetry fallback. In that path the verifier writes:

```text
/dev/shm/shreks-fl9-v2-discovery.<request-id>.request
```

and the already-installed `shreks-telemetry.timer` invokes `shreks-telemetry.service` as the unprivileged `shreks` identity. The verifier may still retrieve the matching fallback result with:

```sh
journalctl -u shreks-telemetry.service -o cat
```

The verifier accepts these trusted read-only completion states:

- `FOUND_COMPATIBLE` — at least one authenticated runtime manifest is compatible with the frozen V2 cohort;
- `HOLD_NO_COMPATIBLE` — authenticated discovery completed but no compatible runtime manifest exists;
- `HOLD_NO_REQUEST_AUTHORITY` — no preserved authenticated V2 request/hydration authority can supply the sealed non-manifest assumptions;
- `HOLD_AMBIGUOUS_REQUEST_AUTHORITY` — more than one distinct authenticated authority tuple exists, so the bridge refuses to choose.

Those outcomes are evidence only. `FOUND_COMPATIBLE` does not itself authorize a fresh V2 scoring request, PAPER promotion, signing, submission, or any live-capital action. **LIVE TRADING: DISABLED.**

The transport boundary remains narrow. Do not add sudoers entries for FL9 discovery. Do not relax ownership, modes, or ACLs on `/etc/shreks` or `/var/lib/shreks`, and do not grant `shreks-deploy` direct access to protected runtime evidence. The privileged read is confined to one release-local startup preflight and result publication occurs only after irreversible drop to `shreks`. No interactive administrator shell is required.

Older deployed releases that do not contain `shreks_brain.telemetry.fl9_v2_discovery_control` report `fl9_v2_discovery_bridge=unavailable` and retain the legacy read-only verification behavior.

### Bind one compatible FL9 V2 discovery authority

When the protected verifier returns a canonical `FOUND_COMPATIBLE` discovery-control result, preserve that exact JSON document as a regular file and bind it before preparing any later proof/request:

```sh
cd /opt/shreks/current

.venv/bin/shreks-fl9-v2-discovery-authority-bind \
  --discovery-result '<exact-canonical-discovery-result.json>' \
  --destination '<new-nonexistent-binding.json>'
```

If more than one compatible runtime-manifest candidate is present, the binder refuses to choose. Supply the exact selected runtime-manifest fingerprint explicitly:

```sh
  --runtime-manifest-fingerprint '<exact-64-hex-runtime-manifest-fingerprint>'
```

The binder requires exact expected/observed release equality, one authenticated request-authority group, authenticated frozen-cohort provenance, and quote identity matching the frozen cohort. It writes one canonical mode-0600 non-overwrite artifact that fingerprints the exact discovery result plus the selected runtime-manifest/hydration authority and source provenance.

The binding is evidence only. It does not authorize model fitting, a V2 scoring retry, champion publication, PAPER promotion, signing/submission, or LIVE trading.

## Rollback

For rollback, select an earlier GitHub Release tag that was previously sealed and verified, then dispatch `Deploy verified Shreks release` with that earlier tag. The same local verification, strict transport, host verification, staging, and health gates apply to rollback; there is no separate bypass path.

If the earlier release is already present under `/opt/shreks/releases/<sha>`, the manager re-verifies its stored manifest and payload before activation. Never replace `/opt/shreks/current` manually and never edit a stored release in place.

## Operational notes

Release delivery proves provenance and rollback mechanics; it does not prove profitability, strategy quality, live readiness, or wallet safety for live capital. G2 remains a PAPER production-operations prerequisite. Any later live-capital phase must separately prove its own credential, risk, recovery, monitoring, emergency-control, and promotion gates before live enablement.
