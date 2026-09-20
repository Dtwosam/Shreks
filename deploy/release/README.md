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

Automatic release creation still does **not** contact the VPS or consume the `production-paper` environment itself. After that release workflow completes successfully through the canonical sealed-main `workflow_run` path, the separate `Deploy verified Shreks release` workflow now continues automatically. The trust boundary remains separate: deployment independently resolves the exact sealed SHA/tag and verifies the immutable GitHub Release before any host contact.

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
