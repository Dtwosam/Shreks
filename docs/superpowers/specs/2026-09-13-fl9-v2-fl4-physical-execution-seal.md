# FL9 V2 Frozen-Cohort FL4 Backfill — Physical Execution Seal

**Date:** 2026-09-13  
**Authority main SHA:** `ec265e2b50bf0050cb16e95eb3db973067931eba`  
**Authorized/deployed runtime SHA:** `4fcbaee62ab33431875109edf98d9b0d5c01cbae`  
**Runtime release path:** `/opt/shreks/releases/4fcbaee62ab33431875109edf98d9b0d5c01cbae`  
**Cohort policy:** `fl9-v2-cohort-acceptance-v1`  
**Cohort artifact fingerprint:** `bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`  
**Accepted-identity fingerprint:** `75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b`  
**Horizon:** `30000 ms`

## Status

The production PAPER VPS completed the authorized frozen-cohort FL4 repair successfully.

The physical execution proved all of the following:

- final pre-quiesce runtime authority gate: **PASS**;
- explicit PAPER quiesce: **PASS**;
- database-holder gate: **PASS**;
- quiesced cohort/scope reauthentication: **PASS**;
- authenticated request construction: **PASS**;
- first FL4 mutation report: **PASS**;
- first-pass postconditions: **PASS**;
- authorized idempotence report: **PASS**;
- idempotence postconditions: **PASS**;
- PAPER runtime restoration: **PASS**;
- FL4 mutation: **COMPLETE**;
- FL4 idempotence: **PROVEN**;
- PAPER promotion: **BLOCKED**;
- LIVE trading: **DISABLED**.

This seal records only the bounded FL4 maintenance result. It does not authorize PAPER promotion, model promotion, strategy/risk changes, wallet access, transaction construction, signing, submission, or LIVE trading.

## Runtime authority proof

Immediately before quiescence, production reported:

- `/opt/shreks/current` -> `/opt/shreks/releases/4fcbaee62ab33431875109edf98d9b0d5c01cbae`;
- `RELEASE_MANIFEST.json.source_sha` -> `4fcbaee62ab33431875109edf98d9b0d5c01cbae`;
- `shreks-observe.service`: active/running, `NRestarts=0`, `ExecMainStatus=0`;
- `shreks-paper-evidence.service`: active/running, `NRestarts=0`, `ExecMainStatus=0`;
- `shreks-paper-campaign.service`: active/running, `NRestarts=0`, `ExecMainStatus=0`;
- current-runtime journal gate: **PASS**;
- campaign configuration capture: **PASS**;
- campaign recovery gate: **PASS**;
- cohort authority gate: **PASS**;
- refreshed FL4 prestate gate: **PASS**.

The active PAPER campaign identity at the privileged prestate gate was:

- `paper_run_id=paper-real-v1-postfix-20260827T204207Z`;
- campaign manifest fingerprint `a1be12204dfdb5efc10f8a309c5fab3820ef72100a38c07ccee0a2da319c38d1`;
- campaign checkpoint sequence `37930`;
- campaign checkpoint state timestamp `1789333127914`.

## Frozen cohort authority

The authenticated frozen cohort reconciled exactly to:

- policy version `fl9-v2-cohort-acceptance-v1`;
- artifact fingerprint `bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`;
- accepted identity fingerprint `75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b`;
- accepted decisions `274334`;
- horizon `30000 ms`;
- frozen source sessions `115,116,117,118,119,120,121,122`;
- cross-session duplicate count `0`;
- latest realtime coverage session `280`.

## Pre-mutation FL4 state

The final pre-quiesce read-only state was:

- total label-v1 rows: `1763328`;
- 30-second label-v1 rows: `146944`;
- exact cohort 30-second labels: `0`;
- exact cohort complete: `0`;
- exact cohort incomplete: `0`;
- out-of-cohort label-v1 rows: `1763328`;
- out-of-cohort key fingerprint algorithm: `sha256(canonical-json-key-lines-v1)`;
- out-of-cohort key SHA-256: `7157aa8ccd05e704a8098dd67f6c71f88f2af275fb7a2f0517ba9561fb9a1f38`;
- SQLite journal mode: `wal`;
- SQLite query-only proof: `1`.

Expected exact post-mutation totals were frozen before mutation as:

- total label-v1 rows: `2037662`;
- 30-second label-v1 rows: `421278`;
- exact cohort rows: `274334`;
- exact cohort complete: `272391`;
- exact cohort incomplete: `1943`.

## Explicit quiesce and holder proof

Production stopped the PAPER runtime in the authorized explicit order and then proved:

- `shreks.target`: inactive;
- `shreks-observe.service`: inactive;
- `shreks-paper-evidence.service`: inactive;
- `shreks-paper-campaign.service`: inactive;
- `shreks-telemetry.timer`: inactive.

The database-holder gate used `lsof` and returned:

`DATABASE_HOLDER_GATE=PASS`

Under quiescence, the privileged read-only FL4 state remained byte-for-byte consistent with the pre-quiesce scope baseline, including the exact out-of-cohort fingerprint.

`QUIESCED_REAUTH_SCOPE_GATE=PASS`

## Authenticated request

Root built the authenticated request under quiescence and handed it to the SQLite-writing observer under the `shreks` service identity.

Request evidence:

- path: `/run/shreks-fl4-backfill/request.json`;
- SHA-256: `d587c54d83f1b5d4bdaea0d746cc301895dae397c8a86f422ea9280ec2c640ee`;
- decision count: `274334`.

`REQUEST_GATE=PASS`

The same immutable request bytes were used for the first invocation and the controlled idempotence invocation.

## First authorized mutation

The first cohort mutation returned exactly:

```json
{
  "schema_name": "shreks.fl9_v2_future_path_backfill_request",
  "schema_version": 1,
  "cohort_artifact_fingerprint_sha256": "bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a",
  "accepted_identity_fingerprint_sha256": "75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b",
  "horizon_ms": 30000,
  "decision_count": 274334,
  "inserted_label_count": 274334,
  "already_existing_label_count": 0,
  "complete_label_count": 272391,
  "incomplete_label_count": 1943
}
```

`FIRST_REPORT_GATE=PASS`

The immediate first-pass read-only post-state was exactly:

- total label-v1 rows: `2037662`;
- 30-second label-v1 rows: `421278`;
- exact cohort 30-second labels: `274334`;
- exact cohort complete: `272391`;
- exact cohort incomplete: `1943`;
- out-of-cohort label-v1 rows: `1763328`;
- out-of-cohort key SHA-256: `7157aa8ccd05e704a8098dd67f6c71f88f2af275fb7a2f0517ba9561fb9a1f38`;
- latest realtime coverage session: `280`.

The out-of-cohort fingerprint remained exactly unchanged from the pre-mutation scope baseline.

`FIRST_POSTCONDITION_GATE=PASS`

## Authorized idempotence proof

The single controlled second invocation against the identical authenticated request returned exactly:

```json
{
  "schema_name": "shreks.fl9_v2_future_path_backfill_request",
  "schema_version": 1,
  "cohort_artifact_fingerprint_sha256": "bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a",
  "accepted_identity_fingerprint_sha256": "75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b",
  "horizon_ms": 30000,
  "decision_count": 274334,
  "inserted_label_count": 0,
  "already_existing_label_count": 274334,
  "complete_label_count": 272391,
  "incomplete_label_count": 1943
}
```

`IDEMPOTENCE_REPORT_GATE=PASS`

The second post-state was identical to the first post-state, including the unchanged out-of-cohort fingerprint.

`IDEMPOTENCE_POSTCONDITION_GATE=PASS`

## Restoration proof

After the authorized first and idempotence invocations, production restored the PAPER runtime successfully:

- `shreks-observe.service`: active/running, `NRestarts=0`, `ExecMainStatus=0`;
- `shreks-paper-evidence.service`: active/running, `NRestarts=0`, `ExecMainStatus=0`;
- `shreks-paper-campaign.service`: active/running, `NRestarts=0`, `ExecMainStatus=0`.

`RESTORATION_GATE=PASS`

The procedure therefore concluded:

```text
FL4_MUTATION=COMPLETE
FL4_IDEMPOTENCE=PROVEN
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

## Duplicate rerun refusal

After the successful physical procedure had already completed, the operator inadvertently started the guarded procedure again.

The repeated invocation observed the already-populated exact cohort before quiescence:

- exact cohort 30-second labels: `274334`;
- exact cohort complete: `272391`;
- exact cohort incomplete: `1943`;
- total label-v1 rows: `2037662`;
- 30-second label-v1 rows: `421278`;
- out-of-cohort key SHA-256 remained `7157aa8ccd05e704a8098dd67f6c71f88f2af275fb7a2f0517ba9561fb9a1f38`.

The precondition gate then stopped immediately with:

`HOLD: exact cohort already has 30-second labels`

This duplicate attempt did not authorize or perform another FL4 mutation. The refusal is consistent with the sealed rule that the physical procedure starts only from an exact cohort with zero 30-second labels and permits only one first mutation plus one controlled idempotence invocation.

## Decision

The physical frozen-cohort FL4 repair is accepted as complete.

The production evidence proves:

1. exact authorized runtime identity;
2. exact frozen cohort authority;
3. zero exact-cohort 30-second labels before mutation;
4. explicit quiescence and no unexpected database holders;
5. exact authenticated request identity;
6. exactly `274334` labels inserted on the first authorized mutation;
7. exact `272391 / 1943` complete/incomplete split;
8. exact expected total/30-second row counts after mutation;
9. byte-stable out-of-cohort scope fingerprint;
10. zero new rows on the authorized idempotence invocation;
11. successful PAPER runtime restoration;
12. fail-closed refusal of a later accidental duplicate procedure start.

The dependent FL9 V2 proof-input/evidence generation may now proceed as a separate slice using this physically repaired FL4 state.

No automatic promotion is implied.

**FL4 physical repair: COMPLETE AND VERIFIED.**  
**FL4 idempotence: PROVEN.**  
**Out-of-cohort scope: UNCHANGED.**  
**PAPER promotion: BLOCKED.**  
**LIVE TRADING: DISABLED.**
