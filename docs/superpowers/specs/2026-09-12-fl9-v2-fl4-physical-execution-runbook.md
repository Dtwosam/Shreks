# FL9 V2 Frozen-Cohort FL4 Backfill — Physical Execution Runbook

## Authority and status

This is a bounded human-operated production-paper maintenance procedure for the already-sealed FL9 V2 frozen-cohort FL4 repair. It adds no deploy-account privilege, no autonomous maintenance service, no PAPER promotion, and no LIVE authority.

The currently authorized runtime release for this repair is:

`0f508e0aca5171c491def3e605b59db0c011666e`

The frozen cohort authority remains:

- artifact path: `/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2`
- artifact fingerprint: `bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`
- accepted identity fingerprint: `75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b`
- accepted decisions: `274334`
- horizon: `30000 ms`
- frozen source sessions: `115,116,117,118,119,120,121,122`
- expected complete labels: `272391`
- expected incomplete labels: `1943`

## Privilege boundary

The frozen cohort artifact is intentionally sealed by the artifact writer as a `0700` directory containing `0600` files. A trusted administrator therefore reads and authenticates the cohort as root. Do not `chmod`, `chown`, copy, or otherwise weaken the artifact to make it readable by the `shreks` service account.

Root may perform read-only cohort authentication and may build the canonical authenticated request document. Root must not run the SQLite-writing observer. The actual FL4 database mutation must remain under the `shreks` service identity so SQLite/WAL/SHM ownership stays consistent with the production runtime.

The authenticated request is the handoff boundary. Under quiescence, root creates exactly one request file in a root-owned runtime directory with group `shreks`, directory mode `0750`, and request mode `0640`. The same immutable request bytes are used for both the first invocation and the idempotence invocation. Remove the request on every exit path.

## Mandatory preconditions

Before any database mutation, a trusted administrator must verify all of the following from the host:

1. `/opt/shreks/current` resolves to the exact authorized release above and its `RELEASE_MANIFEST.json` records the same SHA.
2. `shreks-observe.service`, `shreks-paper-evidence.service`, and `shreks-paper-campaign.service` are healthy with no unexpected restarts since deployment.
3. Recent journals contain no unresolved SQLite contention or runtime-restart signatures.
4. Root reads the frozen cohort with the exact release-local Python package and authenticates the fingerprints, count, horizon, and source sessions above.
5. The production database is opened with SQLite URI `mode=ro` plus `PRAGMA query_only=ON`, and the exact cohort currently has zero 30-second label-v1 rows. Any nonzero value is a HOLD unless separately reconciled before mutation.
6. Capture the complete pre-mutation FL4 totals and a deterministic SHA-256 fingerprint of every label-v1 key outside the accepted cohort. This out-of-cohort fingerprint is the scope baseline.

If any precondition fails, stop. Do not mutate the database.

## Quiesce boundary

Record the initial enabled/active state of `shreks.target`, `shreks-telemetry.timer`, and any currently running `shreks-telemetry.service`. Install an EXIT trap before stopping anything so the recorded runtime/timer state is restored on every success or failure path. The EXIT trap must also remove the temporary authenticated request file and its runtime directory.

Stop the telemetry timer and any running telemetry oneshot, then stop `shreks.target`. Verify the three core PAPER services are inactive and the telemetry timer is inactive.

Check the database, WAL, and SHM files for open holders with `lsof`; if `lsof` is unavailable, use `fuser`. If neither tool is available, or if any unexpected holder remains, this procedure is a HOLD. Do not proceed around an unknown writer.

## Reauthenticate and build the request under quiescence

While quiesced, root must re-read the frozen cohort with the exact release-local Python package and rebuild the authenticated backfill request. Reconfirm the artifact fingerprint, accepted-identity fingerprint, accepted decision count, horizon, and source sessions.

Re-open the database read-only, require the exact cohort 30-second label count to remain zero, and recompute the out-of-cohort label-v1 key fingerprint. Require exact equality with the pre-quiesce baseline.

Then create the authenticated request as root without mutating the database:

```bash
sudo /opt/shreks/current/.venv/bin/python - <<'PY'
from __future__ import annotations

import grp
import hashlib
import json
import os
from pathlib import Path

from shreks_brain.fast_first_champion_v2.models import FastFirstChampionV2Policy
from shreks_brain.fl9_v2_cohort_acceptance import read_fl9_v2_cohort_acceptance
from shreks_brain.fl9_v2_future_path_backfill import build_backfill_request_document

COHORT = Path('/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2')
REQUEST_DIR = Path('/run/shreks-fl4-backfill')
REQUEST = REQUEST_DIR / 'request.json'

if REQUEST.exists() or REQUEST.is_symlink():
    raise FileExistsError(f'request path already exists: {REQUEST}')

artifact = read_fl9_v2_cohort_acceptance(COHORT)
document = build_backfill_request_document(
    artifact,
    policy=FastFirstChampionV2Policy(),
)
payload = (
    json.dumps(
        document,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
        allow_nan=False,
    )
    + '\n'
).encode('utf-8')

shreks_gid = grp.getgrnam('shreks').gr_gid
REQUEST_DIR.mkdir(mode=0o750, parents=True, exist_ok=False)
os.chown(REQUEST_DIR, 0, shreks_gid)
os.chmod(REQUEST_DIR, 0o750)

flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, 'O_NOFOLLOW'):
    flags |= os.O_NOFOLLOW
fd = os.open(REQUEST, flags, 0o640)
try:
    os.fchown(fd, 0, shreks_gid)
    os.fchmod(fd, 0o640)
    with os.fdopen(fd, 'wb', closefd=True) as handle:
        fd = -1
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
finally:
    if fd >= 0:
        os.close(fd)

print(f'request_path={REQUEST}')
print(f'request_sha256={hashlib.sha256(payload).hexdigest()}')
print(f'decision_count={len(document["decisions"])}')
PY
sudo -u shreks test -r /run/shreks-fl4-backfill/request.json
```

Any request-generation or readability failure is a HOLD. Do not alter the cohort permissions to work around it.

## Authorized mutation: first invocation

Execute exactly one first-pass mutation as the `shreks` service identity through the sealed observer binary and authenticated request:

```bash
sudo -u shreks /opt/shreks/current/target/release/shreks-observe \
  populate-cohort-future-path-labels \
  --database /var/lib/shreks/shreks.db \
  --request-json /run/shreks-fl4-backfill/request.json
```

For a previously untouched cohort, the only accepted report is:

- `decision_count=274334`
- `inserted_label_count=274334`
- `already_existing_label_count=0`
- `complete_label_count=272391`
- `incomplete_label_count=1943`

Any mismatch is a HOLD. Do not repair by widening the cohort, changing source checkpoints, deleting labels, or inferring completeness.

## First-pass postconditions

Immediately after the first invocation, verify:

- exact cohort 30-second label-v1 rows: `274334`;
- complete: `272391`;
- incomplete: `1943`;
- total label-v1 row growth equals exactly `274334` relative to the quiesced baseline;
- 30-second label-v1 row growth equals exactly `274334` relative to the quiesced baseline;
- the deterministic out-of-cohort label-v1 key fingerprint is byte-for-byte unchanged from the pre-mutation scope baseline.

The unchanged out-of-cohort fingerprint is mandatory scope proof. An after-only count is insufficient.

## Authorized idempotence invocation

One controlled second invocation of the exact same observer command against the exact same request file is explicitly authorized solely to prove production idempotence.

The only accepted second report is:

- `decision_count=274334`
- `inserted_label_count=0`
- `already_existing_label_count=274334`
- `complete_label_count=272391`
- `incomplete_label_count=1943`

After this second invocation, all database totals and the out-of-cohort fingerprint must be unchanged from the first-pass postconditions. Any new row or fingerprint change is a HOLD.

## Restore and post-restore verification

The EXIT trap must remove `/run/shreks-fl4-backfill/request.json` and its runtime directory and restore the exact recorded PAPER/telemetry state whether the procedure succeeds or fails. After restoration, verify the three core services are active/running, `shreks.target` is active, the expected telemetry timer state is restored, the current release identity is unchanged, and no unexpected restart or failure signature appeared during restoration.

Only after successful restoration and all backfill proofs above may the dependent FL9 V2 proof inputs be regenerated.

## Explicit prohibitions

This procedure does not authorize PAPER promotion, model promotion, strategy/risk changes, wallet access, transaction construction, signing, submission, or LIVE trading. It does not authorize widening the deploy account's sudoers rule or granting it access to `/var/lib/shreks`. It does not authorize changing the frozen cohort artifact ownership or permissions.
