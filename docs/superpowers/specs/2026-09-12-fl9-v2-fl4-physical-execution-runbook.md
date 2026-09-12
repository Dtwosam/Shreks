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

## Mandatory preconditions

Before any database mutation, a trusted administrator must verify all of the following from the host:

1. `/opt/shreks/current` resolves to the exact authorized release above and its `RELEASE_MANIFEST.json` records the same SHA.
2. `shreks-observe.service`, `shreks-paper-evidence.service`, and `shreks-paper-campaign.service` are healthy with no unexpected restarts since deployment.
3. Recent journals contain no unresolved SQLite contention or runtime-restart signatures.
4. The frozen cohort authenticates to the fingerprints, count, horizon, and source sessions above.
5. The exact cohort currently has zero 30-second label-v1 rows. Any nonzero value is a HOLD unless separately reconciled before mutation.
6. Capture the complete pre-mutation FL4 totals and a deterministic SHA-256 fingerprint of every label-v1 key outside the accepted cohort. This out-of-cohort fingerprint is the scope baseline.

If any precondition fails, stop. Do not mutate the database.

## Quiesce boundary

Record the initial enabled/active state of `shreks.target`, `shreks-telemetry.timer`, and any currently running `shreks-telemetry.service`. Install an EXIT trap before stopping anything so the recorded runtime/timer state is restored on every success or failure path.

Stop the telemetry timer and any running telemetry oneshot, then stop `shreks.target`. Verify the three core PAPER services are inactive and the telemetry timer is inactive.

Check the database, WAL, and SHM files for open holders with `lsof`; if `lsof` is unavailable, use `fuser`. If neither tool is available, or if any unexpected holder remains, this procedure is a HOLD. Do not proceed around an unknown writer.

## Reauthenticate under quiescence

While quiesced, re-read the frozen cohort with the exact release-local Python package and rebuild the authenticated backfill request in memory. Reconfirm the artifact fingerprint, accepted-identity fingerprint, accepted decision count, horizon, and source sessions.

Re-query the exact cohort label count and require zero. Recompute the out-of-cohort label-v1 key fingerprint and require exact equality with the pre-quiesce baseline.

## Authorized mutation: first invocation

Execute exactly one first-pass mutation through the release-local entry point and sealed observer binary:

```bash
sudo -u shreks /opt/shreks/current/.venv/bin/shreks-fl9-v2-future-path-backfill \
  --database /var/lib/shreks/shreks.db \
  --cohort /var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2 \
  --observer-binary /opt/shreks/current/target/release/shreks-observe
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

One controlled second invocation of the same authenticated command is explicitly authorized solely to prove production idempotence.

The only accepted second report is:

- `decision_count=274334`
- `inserted_label_count=0`
- `already_existing_label_count=274334`
- `complete_label_count=272391`
- `incomplete_label_count=1943`

After this second invocation, all database totals and the out-of-cohort fingerprint must be unchanged from the first-pass postconditions. Any new row or fingerprint change is a HOLD.

## Restore and post-restore verification

The EXIT trap must restore the exact recorded PAPER/telemetry state whether the procedure succeeds or fails. After restoration, verify the three core services are active/running, `shreks.target` is active, the expected telemetry timer state is restored, the current release identity is unchanged, and no unexpected restart or failure signature appeared during restoration.

Only after successful restoration and all backfill proofs above may the dependent FL9 V2 proof inputs be regenerated.

## Explicit prohibitions

This procedure does not authorize PAPER promotion, model promotion, strategy/risk changes, wallet access, transaction construction, signing, submission, or LIVE trading. It does not authorize widening the deploy account's sudoers rule or granting it access to `/var/lib/shreks`.
