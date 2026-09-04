# G2 verified GitHub-to-VPS release delivery

This runbook bootstraps and operates the Phase G2 PAPER deployment path. GitHub is the release and deployment control plane; the dedicated Linux VPS remains the runtime. The deployment path never creates, copies, reads, edits, or deletes `/etc/shreks/shreks.env`, `/etc/shreks/paper-campaign.json`, or `/var/lib/shreks`.

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

Install the G2 verifier and manager from the exact sealed G2 source checkout. Both files are root-owned and are not writable by the deploy account:

```sh
sudo install -o root -g root -m 0755 deploy/release/release_bundle.py /usr/local/sbin/release_bundle.py
sudo install -o root -g root -m 0755 deploy/release/release_manager.py /usr/local/sbin/shreks-release-manager
sudo chown root:root /usr/local/sbin/release_bundle.py /usr/local/sbin/shreks-release-manager
sudo chmod 0755 /usr/local/sbin/release_bundle.py /usr/local/sbin/shreks-release-manager
```

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

Automatic release creation does **not** contact the VPS, consume the `production-paper` environment, or trigger deployment. Production deployment remains a separate manual action.

Release assets are exactly:

```text
shreks-release-<sha>.tar.gz
shreks-release-<sha>.tar.gz.sha256
RELEASE_MANIFEST.json
```

The top-level release payload intentionally keeps the historical G2 allowlist so an already-installed older root verifier can stage the first release that repairs deployment activation. The exact sealed `deploy/release/release_bundle.py` and `deploy/release/release_manager.py` bytes are embedded inside the already-allowlisted Shreks wheel as:

```text
shreks_brain/_sealed_deploy_control/release_bundle.py
shreks_brain/_sealed_deploy_control/release_manager.py
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

Run the manual `Deploy verified Shreks release` workflow with the existing release tag. The workflow validates the tag, checks out the verifier at that release, downloads the three assets, verifies them before host contact, uses strict pinned host-key checking, copies the assets to `/var/tmp`, and invokes only:

```text
sudo /usr/local/sbin/shreks-release-manager install <archive> <checksum> <manifest>
```

The current release manager re-verifies the bundle, stages `/opt/shreks/releases/<sha>`, constructs the release-local Python environment at its final SHA path, re-verifies stored payloads, installs systemd unit files, atomically switches `/opt/shreks/current`, starts `shreks.target`, and checks health. A repaired manager additionally stops the runtime services explicitly before switching an existing release and verifies runtime **process identity** against the activated immutable release. The two native services must execute the exact binaries inside that release, and every runtime service must have its working directory rooted at that release. If activation fails after a prior release was active, the repaired manager restores the previous verified release and its previous unit files.

## Recover or update sealed deployment control scripts

The root-owned `/usr/local/sbin` verifier and manager are intentionally outside the unprivileged deploy account's write authority. If a verified release contains a deployment-manager fix that must replace an older bootstrapped manager, perform this bounded recovery from a trusted administrator session only after verifying that `/opt/shreks/current` and its `RELEASE_MANIFEST.json` identify the intended immutable release.

The sealed control scripts are transported inside the release's manifest-hashed wheel. Extract only the two fixed members from that verified wheel into a private temporary directory, install them root-owned, then reconcile the already-selected immutable release:

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

## Rollback

For rollback, select an earlier GitHub Release tag that was previously sealed and verified, then dispatch `Deploy verified Shreks release` with that earlier tag. The same local verification, strict transport, host verification, staging, and health gates apply to rollback; there is no separate bypass path.

If the earlier release is already present under `/opt/shreks/releases/<sha>`, the manager re-verifies its stored manifest and payload before activation. Never replace `/opt/shreks/current` manually and never edit a stored release in place.

## Operational notes

Release delivery proves provenance and rollback mechanics; it does not prove profitability, strategy quality, live readiness, or wallet safety for live capital. G2 remains a PAPER production-operations prerequisite. Any later live-capital phase must separately prove its own credential, risk, recovery, monitoring, emergency-control, and promotion gates before live enablement.
