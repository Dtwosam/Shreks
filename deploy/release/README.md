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

## Plan the trusted-admin helper installation ceremony read-only

Before creating any root-private ceremony directory or invoking the installer, a trusted administrator may run the release-local planner:

```sh
CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
CURRENT_SHA="$(basename "$CURRENT_RELEASE")"

sudo "$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-paper-manifest-manager-install-plan" \
  "$CURRENT_SHA"
```

The planner is root-only because it reuses the sealed installation-proof preflight against the protected campaign manifest, narrow deployment sudoers, and read-only `systemctl show` service observations.

It fails closed unless:

- `/opt/shreks/current` is the exact explicit immutable release;
- the release manifest, manifest-hashed Shreks wheel, and sealed manager member authenticate;
- helper status is exactly `ABSENT`;
- the derived root-private evidence directory does not already exist;
- the protected campaign manifest remains valid mode `0640`;
- deployment sudoers still contain only the exact sealed release-manager command;
- observer, PAPER evidence, and PAPER campaign services are healthy;
- helper status remains byte-for-byte identical through the read-only preflight.

A successful plan reports:

```text
status=READY_FOR_TRUSTED_ADMIN_FIRST_INSTALL_CEREMONY
planning_authority=READ_ONLY
installation_authority=NOT_EXERCISED
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The canonical plan binds the exact release/wheel/manager identity, the preflight snapshot fingerprint, campaign/sudoers hashes, service observations, the derived root-private evidence directory, and four exact ordered steps:

```text
create evidence directory
  -> installation-proof prepare
  -> exact release-bound helper installer
  -> installation-proof verify
```

Each executable step is represented as an argv array using the exact current release virtualenv Python plus an explicit module name. Output evidence paths are explicit.

The plan is advisory evidence only. It does not create the evidence directory, does not write proof files, does not execute the installer, and does not verify a post-install state. The embedded preflight snapshot is not a substitute for `installation-proof-pre.json`; the real `prepare` step must run again immediately before the installer.

If helper status is already anything other than `ABSENT`, do not use the first-install plan to repair or replace it. Investigate through the separately sealed status/proof paths instead.

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

## Refresh the exact-release helper installation proof

After a later immutable release changes the release SHA or wheel identity, an earlier helper installation proof is stale even when production verification reports `paper_manifest_manager_status=MATCHED_CURRENT_RELEASE`.

Only after production verification proves the refresh CLI/module belong to the exact active immutable release may a trusted administrator produce a fresh proof without reinstalling the helper.

The refresh requires the helper to already match the exact current release. It fails closed if the helper is absent, has different bytes, or has different metadata. It does not install, replace, chmod, or chown the helper.

Create a new root-private evidence directory and run only the release-local refresh command:

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
CURRENT_SHA="$(basename "$CURRENT_RELEASE")"
PROOF_DIR="/root/shreks-paper-manifest-manager-proof-refresh-$CURRENT_SHA"

if [[ ! "$CURRENT_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "current release identity is invalid" >&2
  exit 2
fi

sudo install -d -o root -g root -m 0700 "$PROOF_DIR"

sudo sh -c '
  set -e
  umask 077
  exec "$1/.venv/bin/shreks-g1c-v2-paper-manifest-manager-install-proof-refresh"     "$2" > "$3/installation-proof.json"
' sh "$CURRENT_RELEASE" "$CURRENT_SHA" "$PROOF_DIR"

sudo cat "$PROOF_DIR/installation-proof.json"
```

The refresh uses the existing exact-release prestate/poststate proof machinery and allows only the installer's `ALREADY_INSTALLED` path. If the helper is not already exact, refresh fails before helper publication.

A successful `installation-proof.json` retains the existing schema and records:

```text
status=VERIFIED
installation_authority=PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

This ceremony produces proof evidence only. It does not create or stage a candidate, transition binding, or readiness receipt; it does not execute readiness; and it does not authorize or invoke manifest rotation.

Do not execute decision-backed readiness merely because this fresh proof exists. The exact reviewed candidate, standard transition binding, decision-backed authority, current-release proof, and current release SHA remain separately required inputs to that later evidence-only ceremony.

## Capture G1C v2 valuation and sizing evidence

After a sealed release containing the evidence-only valuation/sizing tools is active and production verification has proved both release-local script/module paths, a trusted administrator may capture bounded evidence for a later production candidate-value decision.

These operations are deliberately separate from candidate authority.

A quote reference is `REFERENCE_EVIDENCE_ONLY`.

A sizing proposal is `PROPOSAL_EVIDENCE_ONLY`.

This evidence does not authorize production candidate values. Do not run candidate authority from this evidence alone.

### Capture one exact quote-valuation reference

Supply every market-selection input explicitly. There are no production selector defaults.

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
DB="<explicit-observer-sqlite-path>"
CANDIDATE_ID="<explicit-candidate-id>"
AS_OF_UNIX_MS="<explicit-as-of-unix-ms>"
SOURCE="<explicit-market-source>"
VENUE="<explicit-market-venue>"
BASE_MINT="<explicit-base-mint>"
QUOTE_MINT="<explicit-target-quote-mint>"
MAX_AGE_MS="<explicit-freshness-bound-ms>"
EXPECTED_MARKET_ROW_ID="<explicit-exact-row-id-or-empty>"

REFERENCE_DIR="/root/shreks-g1c-v2-quote-valuation-reference"
REFERENCE="$REFERENCE_DIR/quote-valuation-reference.json"

sudo install -d -o root -g root -m 0700 "$REFERENCE_DIR"

if [[ -n "$EXPECTED_MARKET_ROW_ID" ]]; then
  sudo "$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-quote-valuation-reference" \
    --database "$DB" \
    --candidate-id "$CANDIDATE_ID" \
    --as-of-unix-ms "$AS_OF_UNIX_MS" \
    --source "$SOURCE" \
    --venue "$VENUE" \
    --base-mint "$BASE_MINT" \
    --quote-mint "$QUOTE_MINT" \
    --max-age-ms "$MAX_AGE_MS" \
    --expected-market-row-id "$EXPECTED_MARKET_ROW_ID" \
    --destination "$REFERENCE"
else
  sudo "$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-quote-valuation-reference" \
    --database "$DB" \
    --candidate-id "$CANDIDATE_ID" \
    --as-of-unix-ms "$AS_OF_UNIX_MS" \
    --source "$SOURCE" \
    --venue "$VENUE" \
    --base-mint "$BASE_MINT" \
    --quote-mint "$QUOTE_MINT" \
    --max-age-ms "$MAX_AGE_MS" \
    --destination "$REFERENCE"
fi

sudo cat "$REFERENCE"
```

The reference reader uses the existing observer-market read-only SQLite path and derives:

`quote_asset_usd_per_token = base_price_usd / base_price_quote`

from the exact selected persisted market row.

Review the complete reference before using it in any sizing proposal. In particular, review the selected market row, candidate/source/venue/base/quote identity, observation time, freshness boundary, derived USD value, and `reference_fingerprint_sha256`.

### Review multiple exact quote-valuation references

When more than one exact reference has been captured for the same quote mint, source, and frozen `as_of_unix_ms`, do not choose a single venue merely because it is freshest.

A trusted administrator may review three or more existing canonical reference artifacts with the release-local review tool.

The review does not read SQLite and does not capture any new market evidence. It authenticates only the explicit reference files supplied on the command line.

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
REFERENCE_ROOT="<explicit-root-containing-reviewed-reference-files>"
REVIEW_DIR="/root/shreks-g1c-v2-quote-valuation-review"
REVIEW="$REVIEW_DIR/quote-valuation-review.json"

sudo install -d -o root -g root -m 0700 "$REVIEW_DIR"

sudo "$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-quote-valuation-review" \
  --reference "$REFERENCE_ROOT/<explicit-reference-1>.json" \
  --reference "$REFERENCE_ROOT/<explicit-reference-2>.json" \
  --reference "$REFERENCE_ROOT/<explicit-reference-3>.json" \
  --destination "$REVIEW"

sudo cat "$REVIEW"
```

Supply every reference path explicitly. There are no venue/reference selection defaults.

The deterministic review policy is `median_exact_reference_values`. It authenticates each canonical reference, requires one common quote mint/source/as-of boundary, rejects duplicate market rows/fingerprints, and reports exact Decimal min/median/max plus disagreement diagnostics.

The review remains:

```text
status=REVIEW_EVIDENCE_ONLY
candidate_value_authority=NOT_GRANTED
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The review does not authorize production candidate values. The median is a review statistic, not an approved production price. Do not run candidate authority from this review alone.

Only after reviewing the complete artifact may a later evidence-only sizing proposal use an explicitly reviewed value/fingerprint/timestamp. A still-later explicit production candidate-value decision is required before candidate authority.

### Derive one evidence-only entry-sizing proposal from a valuation review

Only after production verification proves the review-backed sizing CLI/module belong to the exact active immutable release may a trusted administrator derive a proposal from one authenticated multi-reference quote-valuation review.

Supply the review path explicitly. Do not copy its median, review fingerprint, or conservative evidence timestamp into the older explicit-reference sizing CLI.

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
SOURCE_MANIFEST="/etc/shreks/paper-campaign.json"
REVIEW="<exact-authenticated-quote-valuation-review.json>"
TARGET_QUOTE_DECIMALS="<reviewed-target-quote-decimals>"

PROPOSAL_DIR="/root/shreks-g1c-v2-review-backed-entry-sizing"
PROPOSAL="$PROPOSAL_DIR/entry-sizing-proposal.json"

sudo install -d -o root -g root -m 0700 "$PROPOSAL_DIR"

sudo "$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-review-backed-entry-sizing" \
  --source-runtime-manifest "$SOURCE_MANIFEST" \
  --review "$REVIEW" \
  --target-quote-decimals "$TARGET_QUOTE_DECIMALS" \
  --destination "$PROPOSAL"

sudo cat "$PROPOSAL"
```

The tool authenticates the canonical review directly. It uses the review's `median_quote_asset_usd_per_token`, review fingerprint (`review_fingerprint_sha256`), and conservative evidence timestamp (`quote_evidence_observed_at_unix_ms`) without re-labeling that provenance as a single explicit reference.

A successful proposal records:

```text
status=PROPOSAL_EVIDENCE_ONLY
quote_evidence_authority=MULTI_REFERENCE_REVIEW
candidate_value_authority=NOT_GRANTED
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The proposal does not authorize production candidate values. Review the proposed raw amount and its complete review-backed evidence chain separately. A later explicit production candidate-value decision may accept, reject, or replace it. Do not run candidate authority from this proposal alone.

### Produce one evidence-only entry-sizing proposal

This remains the backward-compatible single-reference path and records `quote_evidence_authority=EXPLICIT_REFERENCE_ONLY`.

Only after reviewing one exact reference, copy its exact quote value, fingerprint, and observation timestamp into the following explicit inputs.

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
SOURCE_MANIFEST="/etc/shreks/paper-campaign.json"

TARGET_QUOTE_MINT="<reviewed-target-quote-mint>"
TARGET_QUOTE_DECIMALS="<reviewed-target-quote-decimals>"
TARGET_QUOTE_USD_PER_TOKEN="<exact-reviewed-reference-quote-usd-per-token>"
REFERENCE_FINGERPRINT="<exact-reviewed-reference-fingerprint-sha256>"
REFERENCE_OBSERVED_AT_UNIX_MS="<exact-reviewed-reference-observed-at-unix-ms>"

PROPOSAL_DIR="/root/shreks-g1c-v2-entry-sizing-proposal"
PROPOSAL="$PROPOSAL_DIR/entry-sizing-proposal.json"

sudo install -d -o root -g root -m 0700 "$PROPOSAL_DIR"

sudo "$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-entry-sizing-proposal" \
  --source-runtime-manifest "$SOURCE_MANIFEST" \
  --target-quote-mint "$TARGET_QUOTE_MINT" \
  --target-quote-decimals "$TARGET_QUOTE_DECIMALS" \
  --target-quote-usd-per-token "$TARGET_QUOTE_USD_PER_TOKEN" \
  --quote-evidence-fingerprint-sha256 "$REFERENCE_FINGERPRINT" \
  --quote-evidence-observed-at-unix-ms "$REFERENCE_OBSERVED_AT_UNIX_MS" \
  --destination "$PROPOSAL"

sudo cat "$PROPOSAL"
```

The proposal policy is `preserve_source_quote_notional_floor`: it derives the authenticated source quote notional and floors the target raw units so raw-unit rounding cannot increase that notional.

The output still records:

```text
status=PROPOSAL_EVIDENCE_ONLY
candidate_value_authority=NOT_GRANTED
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

Review the proposed raw amount and its exact evidence chain separately. A later explicit production candidate-value decision may accept, reject, or replace it. Do not feed it into the candidate-authority binder merely because the proposal exists.

### Record one explicit G1C v2 candidate-value decision

Only after production verification proves the candidate-value decision CLI/module belong to the exact active immutable release may a trusted administrator review one existing review-backed sizing proposal and record exactly one explicit production candidate-value decision.

The proposal must authenticate with:

`quote_evidence_authority=MULTI_REFERENCE_REVIEW`

A legacy `EXPLICIT_REFERENCE_ONLY` proposal is rejected by this decision tool.

Choose exactly one decision for the reviewed proposal:

- `ACCEPT_PROPOSAL` — select the proposal's exact raw entry amount;
- `REJECT_PROPOSAL` — select no amount and grant no candidate-value authority;
- `REPLACE_PROPOSAL` — select one explicit different positive-u64 raw amount.

Every decision requires a non-empty review reason. Replacement requires `--replacement-entry-input-amount`; accept and reject forbid it.

Example for an explicit ACCEPT decision:

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
PROPOSAL="<exact-authenticated-review-backed-sizing-proposal.json>"
DECISION_DIR="/root/shreks-g1c-v2-candidate-value-decision"
DECISION_FILE="$DECISION_DIR/candidate-value-decision.json"

sudo install -d -o root -g root -m 0700 "$DECISION_DIR"

sudo "$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-candidate-value-decision" \
  --sizing-proposal "$PROPOSAL" \
  --decision ACCEPT_PROPOSAL \
  --decision-reason "<explicit-reviewed-production-value-reason>" \
  --destination "$DECISION_FILE"

sudo cat "$DECISION_FILE"
```

For `REJECT_PROPOSAL`, change only the decision and reason. For `REPLACE_PROPOSAL`, also supply:

```sh
  --replacement-entry-input-amount "<explicit-reviewed-positive-u64-raw-amount>"
```

Do not execute multiple competing decision commands for the same review ceremony. Preserve the one selected canonical decision artifact.

An accepted or replaced decision records:

```text
status=CANDIDATE_VALUE_APPROVED
candidate_value_authority=EXPLICIT_PRODUCTION_DECISION_BOUND
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

A rejected decision records `status=CANDIDATE_VALUE_REJECTED`, no selected raw amount, and `candidate_value_authority=NOT_GRANTED`.

The command authenticates the proposal and binds its proposal fingerprint/file SHA, quote evidence provenance, target quote identity, review reason, and selected amount. It does not invoke candidate authority, author a runtime candidate, create a transition binding, execute readiness, rotate a manifest, score/model-fit, promote PAPER, sign, submit, or enable LIVE.

Do not run candidate authority from this decision alone. A later separate decision-backed bridge must authenticate one approved decision and combine its exact selected quote mint/decimals/raw amount with separately explicit new-run identity/time inputs before candidate authoring can be granted.

### Bind one decision-backed G1C v2 candidate authority

Only after production verification proves the decision-backed candidate-authority CLI/module belong to the exact active immutable release may a trusted administrator bind one approved candidate-value decision to one exact candidate-authoring authority.

Supply only explicit existing authority artifacts plus the new-run identity/time:

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
SOURCE="/etc/shreks/paper-campaign.json"
COHORT="/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2"
REQUEST="<exact-authenticated-v2-request-path>"
DECISION="<exact-approved-candidate-value-decision.json>"

AUTHORITY_DIR="/root/shreks-g1c-v2-decision-backed-candidate-authority"
AUTHORITY="$AUTHORITY_DIR/decision-backed-candidate-authority.json"

PAPER_RUN_ID="<explicit-reviewed-new-run-id>"
START_AT_UNIX_MS="<explicit-reviewed-new-run-start-ms>"

sudo install -d -o root -g root -m 0700 "$AUTHORITY_DIR"

sudo "$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-decision-backed-candidate-authority-bind" \
  --source-runtime-manifest "$SOURCE" \
  --cohort "$COHORT" \
  --v2-host-request-authority "$REQUEST" \
  --candidate-value-decision "$DECISION" \
  --paper-run-id "$PAPER_RUN_ID" \
  --start-at-unix-ms "$START_AT_UNIX_MS" \
  --destination "$AUTHORITY"

sudo cat "$AUTHORITY"
```

There are no raw quote-mint, quote-decimals, or entry-amount inputs. The bridge authenticates the approved decision and takes those exact economics only from its bound fields.

The approved decision must preserve:

```text
status=CANDIDATE_VALUE_APPROVED
candidate_value_authority=EXPLICIT_PRODUCTION_DECISION_BOUND
quote_evidence_authority=MULTI_REFERENCE_REVIEW
```

The bridge then authenticates the source/cohort/request authority through the existing candidate-authority derivation and records the exact derived candidate identity plus both provenance chains.

A successful artifact records:

```text
authority_status=BOUND_EXACT_CANONICAL_CANDIDATE
candidate_value_authority=EXPLICIT_PRODUCTION_DECISION_BOUND
candidate_authoring_authority=DECISION_BACKED_INPUTS_BOUND
installation_authority=NOT_GRANTED
activation_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

This command does not emit or stage a runtime-manifest candidate. It does not create a transition binding, execute readiness, install/activate/rotate a manifest, score/model-fit, promote PAPER, sign, submit, or enable LIVE.

Preserve and review the complete authority artifact separately. A later exact candidate-authoring step must reproduce the candidate manifest SHA/fingerprint committed by this authority. Do not run transition binding from this authority alone.

### Author one exact decision-backed G1C v2 candidate

Only after production verification proves the decision-backed candidate-authoring CLI/module belong to the exact active immutable release may a trusted administrator materialize the one canonical candidate already committed by a reviewed decision-backed candidate authority.

Supply only the canonical source manifest, the exact authenticated authority artifact, and a new private destination:

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
SOURCE="/etc/shreks/paper-campaign.json"
AUTHORITY="<exact-reviewed-decision-backed-candidate-authority.json>"

CANDIDATE_DIR="/root/shreks-g1c-v2-decision-backed-candidate"
CANDIDATE="$CANDIDATE_DIR/runtime-manifest-candidate.json"

sudo install -d -o root -g root -m 0700 "$CANDIDATE_DIR"

sudo "$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-decision-backed-candidate-author" \
  --source-runtime-manifest "$SOURCE" \
  --decision-backed-candidate-authority "$AUTHORITY" \
  --destination "$CANDIDATE"

sudo cat "$CANDIDATE"
```

There are no raw paper-run, timestamp, quote, entry-amount, cohort, request, or decision inputs. The author authenticates the decision-backed authority and takes the exact new-run identity/time and quote economics only from its bound fields.

The author must reproduce the candidate manifest SHA/fingerprint committed by the authority. Any mismatch fails closed.

The source manifest must also match the source SHA/fingerprint/paper-run identity committed by the authority. The source and authority are re-checked for byte stability before the candidate is persisted.

The destination is write-once and private. A successful invocation writes only the exact canonical mode-0600 runtime-manifest candidate file.

This command does not create a transition binding, execute readiness, install/activate/rotate a manifest, score/model-fit, promote PAPER, sign, submit, or enable LIVE.

Preserve and review the candidate separately. Do not run transition binding from this candidate alone. A later transition-binding step must authenticate this exact candidate together with the authority chain and the existing cohort/request transition requirements.

### Bind one exact decision-backed G1C v2 transition

Only after production verification proves the decision-backed transition-binding CLI/module belong to the exact active immutable release may a trusted administrator bind the exact authored candidate through the already-reviewed decision-backed authority and existing frozen cohort/request compatibility checks.

Use the protected source, the exact reviewed candidate, its exact reviewed decision-backed authority, the frozen cohort directory, the authenticated request authority, and a new root-private destination:

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
SOURCE="/etc/shreks/paper-campaign.json"
CANDIDATE="<exact-reviewed-decision-backed-candidate.json>"
AUTHORITY="<exact-reviewed-decision-backed-candidate-authority.json>"
COHORT="/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2"
REQUEST="<exact-authenticated-v2-request-path>"

BINDING_DIR="/root/shreks-g1c-v2-decision-backed-transition"
BINDING="$BINDING_DIR/transition-binding.json"

sudo install -d -o root -g root -m 0700 "$BINDING_DIR"

sudo "$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-decision-backed-transition-bind" \
  --source-runtime-manifest "$SOURCE" \
  --candidate-runtime-manifest "$CANDIDATE" \
  --decision-backed-candidate-authority "$AUTHORITY" \
  --cohort "$COHORT" \
  --v2-host-request-authority "$REQUEST" \
  --destination "$BINDING"

sudo cat "$BINDING"
```

The cohort input is the frozen cohort directory, not a single file.

There are no raw paper-run, timestamp, quote, entry-amount, decision, review, or sizing inputs. The bridge authenticates the source, candidate, and decision-backed authority; delegates the cohort/request compatibility assessment to the existing canonical transition binder; then requires the resulting source/candidate/cohort/request provenance to equal the decision-backed authority.

A successful invocation writes the existing standard transition-binding schema, `shreks.g1c_v2_runtime_manifest_transition_binding` version 1, as one write-once mode-0600 private file.

The standard binding continues to record:

```text
installation_authority=NOT_GRANTED
activation_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

This command does not execute rotation-readiness, install/activate/rotate a runtime manifest, retry scoring/model fitting, promote PAPER, access wallets, sign or submit transactions, or enable LIVE.

Preserve and review the binding separately. Do not execute rotation-readiness merely because this binding exists; readiness remains a separate ceremony that must authenticate the exact candidate/binding, exact current release, and fresh release-bound helper installation proof.

## Bind explicit G1C v2 candidate inputs

After a sealed release containing the candidate-input authority binder is active and production verification has proved that binder's release-local script/module provenance, a trusted administrator may bind one **separately reviewed** set of explicit new-run values.

The binder does not choose production candidate values. It does not infer them from the frozen cohort, historical USDC hydration evidence, recent quote evidence, unit tests, or example values. Every new-run value below is an operator-supplied placeholder until a separate reviewed production-value decision establishes the exact value.

The binder authenticates the existing v1 source, frozen FL9 V2 cohort, and preserved V2 request authority; requires the explicit target quote mint to equal the frozen cohort quote mint; derives the canonical v2 candidate only in memory; and writes one immutable private authority artifact. It does not stage candidate bytes, write a transition binding, execute rotation-readiness, replace the protected manifest, or grant downstream authority.

Use a root-private destination and invoke only from the exact current release:

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
SOURCE="/etc/shreks/paper-campaign.json"
COHORT="/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2"
REQUEST="<exact-authenticated-v2-request-path>"

AUTHORITY_DIR="/root/shreks-g1c-v2-candidate-authority"
AUTHORITY="$AUTHORITY_DIR/candidate-authority.json"

PAPER_RUN_ID="<explicit-reviewed-new-run-id>"
START_AT_UNIX_MS="<explicit-reviewed-new-run-start-ms>"
QUOTE_ASSET_MINT="<explicit-reviewed-target-quote-mint>"
QUOTE_ASSET_DECIMALS="<explicit-reviewed-target-quote-decimals>"
ENTRY_INPUT_AMOUNT="<explicit-reviewed-raw-entry-input-amount>"

sudo install -d -o root -g root -m 0700 "$AUTHORITY_DIR"

sudo "$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-runtime-manifest-candidate-authority-bind" \
  --source-runtime-manifest "$SOURCE" \
  --cohort "$COHORT" \
  --v2-host-request-authority "$REQUEST" \
  --paper-run-id "$PAPER_RUN_ID" \
  --start-at-unix-ms "$START_AT_UNIX_MS" \
  --quote-asset-mint "$QUOTE_ASSET_MINT" \
  --quote-asset-decimals "$QUOTE_ASSET_DECIMALS" \
  --entry-input-amount "$ENTRY_INPUT_AMOUNT" \
  --destination "$AUTHORITY"

sudo cat "$AUTHORITY"
```

The placeholders above are intentionally not defaults. In particular, do not substitute unit-test values, the active USDC runtime's decimals/raw amount, or historical hydration-policy values for the reviewed production inputs.

A successful `candidate-authority.json` proves only that one explicit input set is bound to the exact authenticated source/cohort/request authority and to one exact canonically derivable v2 candidate identity. It records:

```text
candidate_authoring_authority=EXPLICIT_INPUTS_BOUND
installation_authority=NOT_GRANTED
activation_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The authority binder itself does not emit or stage the candidate runtime-manifest file. After one exact production-value authority artifact has been separately reviewed and accepted, use the existing canonical candidate-authoring path to emit those exact candidate bytes, assess that exact candidate read-only against the frozen cohort/request authority, and create the existing immutable transition binding.

Do not run rotation-readiness until the exact canonical candidate file and its exact canonical transition binding already exist and have been staged as immutable regular files.

### Prove exact decision-backed G1C v2 rotation readiness

Only after production verification proves the decision-backed readiness CLI/module belong to the exact active immutable release, and only after the exact reviewed decision-backed candidate plus its exact standard transition binding already exist, a trusted administrator may request evidence-only readiness for that authority chain.

A **fresh exact-release installation proof** is mandatory. Because every sealed deployment changes the current release SHA and wheel identity, do not reuse an installation proof from an earlier release even if the installed manifest-manager bytes still match.

Use the exact reviewed candidate, binding, and decision-backed authority together with the current-release helper proof:

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
CURRENT_SHA="$(basename "$CURRENT_RELEASE")"

CANDIDATE="<exact-reviewed-decision-backed-candidate.json>"
BINDING="<exact-reviewed-decision-backed-transition-binding.json>"
AUTHORITY="<exact-reviewed-decision-backed-candidate-authority.json>"
INSTALL_PROOF="/root/shreks-paper-manifest-manager-install-$CURRENT_SHA/installation-proof.json"

READINESS_DIR="/root/shreks-g1c-v2-decision-backed-rotation-readiness-$CURRENT_SHA"
READINESS="$READINESS_DIR/rotation-readiness.json"

if [[ ! "$CURRENT_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "current release identity is invalid" >&2
  exit 2
fi

sudo install -d -o root -g root -m 0700 "$READINESS_DIR"

sudo sh -c '
  set -e
  umask 077
  exec "$1/.venv/bin/shreks-g1c-v2-decision-backed-rotation-readiness" \
    --candidate-runtime-manifest "$2" \
    --transition-binding "$3" \
    --decision-backed-candidate-authority "$4" \
    --installation-proof "$5" \
    --expected-release-source-sha "$6" \
    > "$7"
' sh \
  "$CURRENT_RELEASE" \
  "$CANDIDATE" \
  "$BINDING" \
  "$AUTHORITY" \
  "$INSTALL_PROOF" \
  "$CURRENT_SHA" \
  "$READINESS"

sudo cat "$READINESS"
```

There is no operator-supplied binding fingerprint. The wrapper authenticates the standard transition binding and **derives the binding fingerprint from the authenticated binding** before delegating to the already-sealed readiness proof.

There are no raw paper-run, timestamp, quote, entry-amount, decision, review, or sizing inputs. The wrapper authenticates the candidate, standard binding, and decision-backed authority, requires their provenance to agree, and then delegates the current-release/helper/service/G7/preflight checks to the existing readiness implementation.

A successful receipt remains the existing standard readiness schema and records:

```text
status=READY_EVIDENCE_ONLY
installation_authority=PROVEN
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

This evidence-only command does not invoke the manifest manager, does not replace the active runtime manifest, and does not grant manifest-rotation authority. Preserve and review the readiness receipt separately before any later, explicitly authorized rotation decision.

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
