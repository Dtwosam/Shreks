# FL9 V2 Cohort Acceptance Design

**Date:** 2026-09-08  
**Base main SHA:** `f02564f8b0ff7aac951cdd8588bd3dd157a51345`  
**Status:** DESIGN — approved in chat, pending written-spec review  
**Scope:** input-only immutable cohort acceptance only  
**LIVE:** DISABLED

## 1. Purpose

Create a deterministic, versioned, read-only FL9 V2 cohort-acceptance artifact that freezes the exact first-champion input population **before** any FL4 target values, future returns, model metrics, PnL, or model training are read.

The artifact is the authority boundary between:

1. authenticated point-in-time FL9 tradable-universe admission; and
2. later V2 first-champion target/model evaluation.

The accepted cohort must be reproducible from the sealed production evidence, must preserve exact decision identities rather than only timestamp ranges, and must fail closed if the immutable source evidence drifts from the precommitted input-only checkpoint.

This design does not train a model and does not authorize PAPER promotion or LIVE.

## 2. Evidence that motivates acceptance

The physically deployed sealed release is:

`f02564f8b0ff7aac951cdd8588bd3dd157a51345`

Physical production-paper verification showed:

- release identity: PASS;
- manifest source SHA: PASS;
- runtime process identity: PASS;
- all core services active with zero restarts;
- post-deploy error journal lines: 0;
- FL8.3 V2 import: PASS;
- FL9 tradable-universe v1 fingerprint: exact;
- V2 feature identity firewall fingerprint: exact;
- coverage session 123 is mutable;
- sessions 115 through 122 are immutable.

The input-only immutable V2 preflight over sessions 115–122 produced:

### Raw immutable PumpSwap population

- raw PumpSwap decisions: 504,716;
- cross-session overlap duplicates: 0;
- raw unique mints: 394.

### FL9 v1 eligible population

- eligible decisions: 274,334;
- eligible unique mints: 146;
- missing fresh exact market snapshot: 176,299;
- below minimum liquidity: 52,974;
- below minimum h24 volume: 1,109.

Eligible concentration:

- top-1 mint share: 8.0406%;
- top-3: 19.3465%;
- top-5: 26.5213%;
- top-10: 39.0987%;
- HHI: 0.026055;
- effective mint count: 38.3806.

### Input-only deterministic 60/20/20 shape

Using equal-timestamp buckets and the sealed first-champion 60/20/20 objective:

- training cut: `1788892302791`;
- validation cut: `1788898931418`;
- raw training: 164,645 rows / 97 mints;
- raw validation: 54,858 rows / 34 mints;
- raw TEST: 54,831 rows / 34 mints.

Cross-partition reuse:

- shared mints: 17;
- shared actors: 9,557;
- shared signatures: 0.

Under FL8.3 V2 signature-only quarantine:

- training quarantined: 0;
- validation quarantined: 0;
- TEST quarantined: 0;
- surviving shared signatures: 0.

### V2 novelty evidence

Novelty is relative to **raw training only**.

Validation:

- unseen-mint rows: 49,754;
- unseen mints: 24;
- seen-mint rows: 5,104;
- seen mints: 10;
- seen-actor rows: 23,416;
- unseen-actor rows: 31,442;
- null-actor rows: 0.

TEST:

- unseen-mint rows: 54,828;
- unseen mints: 31;
- seen-mint rows: 3;
- seen mints: 3;
- seen-actor rows: 11,841;
- unseen-actor rows: 42,990;
- null-actor rows: 0.

No target values, future returns, future-path labels, model performance, PnL, or model training were inspected to produce these values.

## 3. Selected architecture

Introduce a sibling, versioned input-only artifact:

`fl9-v2-cohort-acceptance-v1`

Conceptual schema:

`shreks.fl9_v2_cohort_acceptance`

Schema version:

`1`

The artifact is produced by a pure read-only Python builder that consumes:

- the observer SQLite database;
- an explicit immutable coverage-session policy;
- `fl9-tradable-universe-v1`;
- the sealed V2 feature-identity firewall fingerprint;
- the explicit forecast horizon;
- the explicit frozen selection timestamp;
- an explicit structural evidence-floor policy.

It does **not** consume:

- FL4 future-path labels;
- training bundles;
- FL8.2 trainers;
- validation engines that require labels;
- evaluation contexts;
- trading economics;
- PAPER ledgers;
- promotion state;
- model artifacts;
- PnL.

The artifact freezes exact accepted decision identities and exact partition/novelty membership.

## 4. Why a separate acceptance artifact

Three approaches were considered.

### 4.1 Selected: separate input-only cohort artifact

Advantages:

- creates a hard physical/code boundary before target access;
- makes the exact eligible identities durable and reviewable;
- prevents a later host clock from silently admitting newer rows;
- prevents the training runner from re-running eligibility with a changed DB state;
- makes session-gap exclusion explicit;
- allows later target/model code to fail closed against a frozen identity population.

### 4.2 Rejected: embed acceptance directly in first-champion training

This would reduce file count but blur the source/target firewall. A bug or future refactor could let target availability or model outcomes influence population selection.

### 4.3 Rejected: keep acceptance as an operator-only VPS script

The current script is useful evidence, but a first genuine champion needs a durable, versioned artifact with canonical fingerprints. An ad-hoc transcript is not enough authority for training.

## 5. Frozen immutable source boundary

The cohort source is exactly coverage sessions:

`115,116,117,118,119,120,121,122`

No earlier session and no later session belongs to this cohort.

The builder must require:

- all eight session rows exist;
- all eight session IDs are exact and unique;
- an immutability boundary exists strictly after 122;
- equivalently, `MAX(fast_realtime_coverage_sessions.session_id) >= 123`;
- source session metadata matches the frozen checkpoint below.

Frozen session metadata:

| Session | Provider | Process sequence | First observed ms | Last observed ms | Notifications |
|---:|---|---:|---:|---:|---:|
| 115 | `solana_public` | 1 | 1788878323281 | 1788878840118 | 20,710 |
| 116 | `solana_public` | 1 | 1788883195692 | 1788883318307 | 269 |
| 117 | `solana_public` | 2 | 1788883321082 | 1788886814126 | 190,896 |
| 118 | `solana_public` | 3 | 1788887193636 | 1788890813557 | 196,433 |
| 119 | `solana_public` | 4 | 1788890820688 | 1788891310394 | 30,697 |
| 120 | `solana_public` | 5 | 1788891317263 | 1788892489553 | 62,883 |
| 121 | `solana_public` | 6 | 1788895790049 | 1788900928410 | 279,491 |
| 122 | `solana_public` | 1 | 1788900968708 | 1788902289834 | 64,497 |

Session gaps are intentional evidence boundaries. The builder reads the **union of these exact eight session time windows**, not one broad `MIN(first)..MAX(last)` interval.

Therefore rows in gaps between sessions cannot enter the accepted population merely because their timestamps fall between the cohort start and end.

## 6. Frozen forecast horizon and selection clock

The first genuine V2 challenger horizon is frozen at:

`30,000 ms`

This is one of the sealed FL4 default future-path horizons.

The cohort's exclusive TEST end is frozen at one millisecond after the final immutable source observation:

`test_end_unix_ms = 1788902289835`

The frozen selection timestamp is therefore:

`selection_at_unix_ms = 1788902319835`

because:

`selection_at_unix_ms - horizon_ms = test_end_unix_ms`

The cohort lower bound is:

`minimum_decision_observed_at_unix_ms = 1788878323281`

No host wall clock is allowed to change these values for this accepted cohort.

Later execution time may be after this timestamp; that does not admit additional decisions.

## 7. Raw PumpSwap population construction

For each of the eight exact source windows, select only:

`venue = 'pump_swap'`

from `fast_events`.

Canonical raw identity key:

`(decision_signature, decision_ordinal)`

The canonical decision identity is the existing seven-field FL8.1 identity:

1. signature;
2. ordinal;
3. sequence;
4. mint;
5. quote mint;
6. venue;
7. decision observed timestamp.

If the same signature+ordinal appears in more than one source window:

- identical rows may be deduplicated deterministically;
- contradictory rows fail closed.

The accepted checkpoint expects:

- raw rows across windows: exactly 504,716;
- cross-session overlap duplicates: exactly 0;
- raw unique mints: exactly 394.

These exact checkpoint counts are drift detectors, not model-quality thresholds.

A mismatch fails artifact creation and requires a new input-only investigation. The builder must not silently accept a changed immutable history.

## 8. Authenticated FL9 tradable-universe admission

Every canonical raw decision is assessed through the sealed:

`fl9-tradable-universe-v1`

Required policy fingerprint:

`abfc6d21eb27d722956fbd267a10f352c887a909b3865a7a295eff95631777e4`

No eligibility rule is reimplemented inside the cohort builder.

The assessment remains:

- PumpSwap only;
- verified Pump.fun migration;
- exact canonical PumpSwap market;
- market evidence point-in-time at or before decision;
- snapshot age <= 60,000 ms;
- liquidity >= $3,000;
- trailing h24 volume >= $1,000;
- missing/ambiguous/contradictory evidence fails closed.

The accepted checkpoint expects exactly:

- eligible: 274,334;
- missing fresh exact snapshot: 176,299;
- below minimum liquidity: 52,974;
- below minimum h24 volume: 1,109;
- eligible unique mints: 146.

Any change to the FL9 policy version/fingerprint requires a new cohort-acceptance policy version.

## 9. Exact eligible identity evidence

The artifact must preserve every accepted decision identity in canonical order.

For each eligible decision it must also preserve a deterministic fingerprint of the exact tradable-universe assessment evidence used to admit that decision.

The per-decision assessment fingerprint must cover, at minimum:

- decision identity;
- tradable-universe policy version/fingerprint;
- decision venue;
- verified migration identity and observation timestamp;
- selected canonical market identity/source;
- selected market snapshot observation timestamp;
- snapshot age at decision;
- liquidity USD;
- trailing h24 volume USD;
- final eligibility reason.

Raw future target or outcome values are forbidden from this material.

The accepted eligible-identity population itself receives a canonical SHA-256 fingerprint.

## 10. Deterministic 60/20/20 partition

The planner operates only on the exact eligible identity population and only on rows satisfying:

`1788878323281 <= decision_observed_at_unix_ms < 1788902289835`

Because the source input is already restricted to sessions 115–122, the timestamp rule cannot pull rows from session gaps.

The boundary algorithm remains the sealed first-champion rule:

1. group equal decision timestamps;
2. never split equal timestamps;
3. choose the eligible cumulative boundary nearest 60%;
4. choose the eligible cumulative boundary nearest 80%;
5. use half-open intervals.

The accepted input-only checkpoint produced:

- training cut: `1788892302791`;
- validation cut: `1788898931418`.

Artifact creation must reproduce those exact cuts.

If it does not, fail closed. Do not search another split.

Frozen partitions:

- training: `[1788878323281, 1788892302791)`;
- validation: `[1788892302791, 1788898931418)`;
- TEST: `[1788898931418, 1788902289835)`.

Expected raw counts:

- training: 164,645;
- validation: 54,858;
- TEST: 54,831.

## 11. FL8.3 V2 signature isolation

Mint and actor recurrence do not remove rows.

Exact transaction/event isolation remains mandatory.

A signature appearing in more than one partition is shared.

Every row carrying a shared signature is quarantined from every affected partition.

The preflight checkpoint expects:

- shared signatures: 0;
- training quarantined: 0;
- validation quarantined: 0;
- TEST quarantined: 0;
- surviving shared signatures: 0.

The artifact format still supports non-empty signature quarantine so the policy remains general and fail-closed.

Novelty classification is computed relative to **raw training**, exactly as sealed by FL8.3 V2, not relative to post-quarantine training.

## 12. V2 feature-identity firewall

Required firewall:

`fl8.3-feature-identity-firewall-v1`

Required fingerprint:

`e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0`

The cohort artifact builder must authenticate this firewall even though it does not train a model.

This binds the accepted cohort to the exact identity-blind feature schema under which recurring mint/actor rows are permitted.

If the model feature schema changes, the cohort artifact cannot silently remain authoritative for the new schema.

## 13. Structural evidence-floor policy

Freeze:

`fl9-v2-cohort-evidence-floor-v1`

The following floors are selected **before target/model/PnL inspection**.

| Evidence | Frozen minimum | Current input-only value |
|---|---:|---:|
| Total eligible rows | 250,000 | 274,334 |
| Raw training rows | 150,000 | 164,645 |
| Raw validation rows | 50,000 | 54,858 |
| Raw TEST rows | 50,000 | 54,831 |
| Unseen-mint validation rows | 40,000 | 49,754 |
| Unseen validation unique mints | 20 | 24 |
| Unseen-mint TEST rows | 40,000 | 54,828 |
| Unseen TEST unique mints | 25 | 31 |

All eight floors are mandatory.

They are not tunable after target/model evidence is observed.

If the exact cohort fails one of these floors during artifact creation, artifact creation fails. The builder does not lower the floor or search another split.

## 14. Concentration is diagnostic, not an admission threshold

No hard mint-concentration threshold is introduced in V1 of this acceptance policy.

The artifact records concentration diagnostics for:

- full eligible population;
- raw training;
- raw validation;
- raw TEST;
- post-signature training;
- post-signature validation;
- post-signature TEST;
- unseen-mint validation;
- unseen-mint TEST.

At minimum record:

- row count;
- unique mint count;
- top-1/top-3/top-5/top-10 shares;
- HHI;
- effective mint count.

Reason:

- the source-of-truth does not authorize inventing a hard concentration threshold;
- the current raw training population is materially broader than the old V1 post-quarantine population;
- unseen-mint TEST provides the direct required stress test against mint-specific overfit.

No mint balancing is added by this slice.

## 15. Novelty classifications

Mint novelty is relative to raw training only.

For validation and TEST:

- unseen mint: mint absent from raw training;
- seen mint: mint present in raw training.

Actor novelty is diagnostic only:

- seen actor: non-null actor present in raw training;
- unseen actor: non-null actor absent from raw training;
- null actor: actor is null.

Actor novelty cannot delete or reweight rows.

Expected checkpoint counts:

### Validation

- rows: 54,858;
- unique mints: 34;
- unseen-mint rows: 49,754;
- unseen mints: 24;
- seen-mint rows: 5,104;
- seen mints: 10;
- seen actors: 23,416;
- unseen actors: 31,442;
- null actors: 0.

### TEST

- rows: 54,831;
- unique mints: 34;
- unseen-mint rows: 54,828;
- unseen mints: 31;
- seen-mint rows: 3;
- seen mints: 3;
- seen actors: 11,841;
- unseen actors: 42,990;
- null actors: 0.

The artifact stores deterministic fingerprints for:

- all accepted identities;
- training identities;
- validation identities;
- TEST identities;
- unseen-mint validation identities;
- seen-mint validation identities;
- unseen-mint TEST identities;
- seen-mint TEST identities;
- signature-quarantined identities.

## 16. Artifact layout

Use an immutable directory artifact rather than one giant JSON object.

Conceptual files:

- `manifest.json`
- `accepted-decisions.jsonl`
- `signature-quarantine.jsonl`

### 16.1 accepted-decisions.jsonl

One canonical line per accepted post-signature-quarantine decision.

Each line contains only input-side evidence:

- seven-field decision identity;
- partition: training / validation / test;
- assessment fingerprint;
- mint novelty for future partitions: seen / unseen / not_applicable;
- actor novelty: seen / unseen / null / not_applicable.

The file is sorted by the existing decision identity chronology key.

No target value, label completeness, return, model prediction, or PnL field is permitted.

### 16.2 signature-quarantine.jsonl

One canonical line per quarantined decision, if any.

Each line contains:

- decision identity;
- affected partition;
- shared signature.

For the accepted 115–122 checkpoint this file is expected to be empty, but its exact empty-file SHA-256 is still recorded.

### 16.3 manifest.json

The manifest covers at least:

- schema name/version;
- policy version;
- structural floor policy version;
- exact source session IDs and frozen metadata;
- required immutability boundary;
- raw checkpoint counts;
- FL9 tradable-universe policy version/fingerprint;
- V2 feature-firewall version/fingerprint;
- horizon;
- cohort lower bound;
- TEST exclusive end;
- frozen selection timestamp;
- exact training/validation cuts;
- raw and post-signature counts;
- structural floors and pass/fail results;
- concentration diagnostics;
- novelty counts;
- all subset logical fingerprints;
- assessment-evidence aggregate fingerprint;
- JSONL file SHA-256 values;
- final artifact fingerprint.

The artifact fingerprint covers all semantic manifest material plus the exact file hashes.

## 17. Determinism

Equivalent immutable source evidence must produce byte-identical artifacts independent of:

- SQLite source row order;
- current wall clock;
- current latest session ID, provided it remains >=123;
- process ID;
- host path;
- repeated execution.

No generated-at timestamp belongs in the canonical artifact.

The builder must refuse overwrite of an existing destination.

## 18. Drift handling

The builder fails closed if any frozen input checkpoint drifts, including:

- missing target session;
- changed session metadata;
- target session no longer immutable;
- changed raw row count;
- changed cross-session duplicate count;
- changed eligible count/reason counts;
- changed eligible unique mint count;
- changed 60/20/20 cuts;
- changed raw partition counts;
- changed signature overlap/quarantine counts;
- changed novelty counts;
- wrong policy/firewall fingerprint;
- structural floor failure.

A drift does not authorize automatic adaptation.

The response is a new input-only root-cause audit and, if justified, a separately versioned acceptance policy.

## 19. Source and authority isolation

The cohort-acceptance package may import only input-side/read-only modules required for:

- SQLite read access;
- FastEvent identity material;
- FL9 tradable-universe assessment;
- FL8.3 V2 feature-firewall authentication;
- canonical encoding/fingerprinting.

The source tree for this slice must fail an authority test if it imports or references:

- future-path label builders/readers;
- `FastTrainingBundle`;
- FL8.2 trainer/inference;
- FL8.3 V1/V2 model-running engines;
- evaluation contexts/reports;
- training economics;
- champion builder;
- promotion/registry;
- PAPER executor;
- signing/submission;
- LIVE runtime authority.

SQLite must be opened with `mode=ro` and `PRAGMA query_only = ON`.

## 20. Downstream target-availability floors precommitted now

The cohort artifact itself cannot inspect target availability.

However, this design precommits the following later **per-target** TEST scoring floors before any target/model evidence is read:

- natural TEST scored observations: at least 40,000;
- unseen-mint TEST scored observations: at least 35,000.

These apply to every required first-champion target/model member in the later V2 first-champion integration.

If a target later fails either floor:

- do not lower the threshold;
- do not change the cohort;
- do not change the split;
- do not pick a different horizon based on performance;
- fail the first-champion attempt and investigate target/evidence coverage.

These target floors are not enforced by the input-only cohort builder because doing so would violate its authority boundary.

## 21. Downstream V2 first-champion contract

This slice does not modify the existing V1 first-champion request, plan, builder, or host-run schemas.

After the cohort artifact is sealed and physically produced:

1. design a separately versioned V2 first-champion host/request path;
2. require the exact cohort artifact fingerprint;
3. require exact reconciliation between training-bundle feature identities and the accepted cohort identities;
4. forbid the V2 runner from reselecting tradable-universe membership;
5. use the frozen 30,000 ms horizon and frozen split;
6. run one V2 model artifact per required FL8.2 target/family;
7. evaluate natural TEST;
8. evaluate the exact unseen-mint TEST subset using the same predictions;
9. enforce the precommitted 40,000 / 35,000 per-target scoring floors;
10. only then inspect realistic cost-adjusted economics.

V1 host-request bytes and V1 evidence semantics remain unchanged.

## 22. TDD requirements

Implementation requires independent RED -> GREEN proof for at least:

1. exact schema/policy/floor versions;
2. exact source session set required;
3. session metadata drift fails;
4. session 122 fails immutability without a later session;
5. later current sessions do not change artifact bytes;
6. broad timestamp gaps do not admit rows outside exact source windows;
7. raw canonical identity duplicates deduplicate only when identical;
8. contradictory duplicate identity fails;
9. exact FL9 v1 policy fingerprint required;
10. FL9 eligibility is called, not reimplemented;
11. exact preflight raw/reason checkpoint drift fails;
12. exact eligible population count/mint drift fails;
13. exact 30,000 ms horizon required;
14. exact frozen selection/test-end relationship required;
15. deterministic equal-timestamp 60/20/20 cuts reproduce the frozen cuts;
16. alternate cut search is forbidden;
17. repeated mints retained;
18. repeated actors retained;
19. shared signatures quarantined;
20. surviving cross-partition signature fails;
21. novelty is relative to raw training only;
22. validation-first mint remains unseen in TEST if absent from training;
23. actor null/seen/unseen diagnostics reconcile;
24. all eight structural floors enforced;
25. concentration is recorded but cannot reject by an invented threshold;
26. accepted identity/subset fingerprints deterministic;
27. assessment fingerprints deterministic;
28. source row ordering does not alter artifact bytes;
29. current wall clock does not alter artifact bytes;
30. destination overwrite fails;
31. malformed canonical JSON/JSONL fails decode;
32. file SHA mismatch fails artifact read;
33. artifact fingerprint mismatch fails artifact read;
34. no target/label/trainer/evaluation/economics/PAPER/LIVE authority in package source;
35. the production-shaped 115–122 fixture reproduces the expected checkpoint counts.

## 23. Acceptance sequence

After implementation:

1. RED -> GREEN under TDD;
2. exact-head CI all four gates;
3. merge with guarded head SHA;
4. merged-main CI all four gates;
5. seal a release containing the acceptance builder;
6. deploy exact sealed release to production-paper;
7. verify physical release SHA/services;
8. run the builder against the production observer DB in read-only mode;
9. produce the exact cohort artifact;
10. read it back and verify every file/fingerprint;
11. record the artifact fingerprint in a docs/evidence seal;
12. only after that begin the separate V2 first-champion integration design.

No target values are read in steps 1–11.

## 24. Frozen policy summary

### Cohort

- sessions: 115–122 exactly;
- required later session: >=123;
- cohort start: 1788878323281;
- test end exclusive: 1788902289835;
- horizon: 30,000 ms;
- frozen selection timestamp: 1788902319835.

### Split

- training cut: 1788892302791;
- validation cut: 1788898931418.

### Structural floors

- total eligible >=250,000;
- training >=150,000;
- validation >=50,000;
- TEST >=50,000;
- unseen validation rows >=40,000;
- unseen validation mints >=20;
- unseen TEST rows >=40,000;
- unseen TEST mints >=25.

### Later per-target floors

- natural TEST scored >=40,000;
- unseen-mint TEST scored >=35,000.

### Policies

- tradable universe: `fl9-tradable-universe-v1`;
- tradable-universe fingerprint:
  `abfc6d21eb27d722956fbd267a10f352c887a909b3865a7a295eff95631777e4`;
- validation: `fl8.3-chronological-generalization-v2`;
- feature firewall: `fl8.3-feature-identity-firewall-v1`;
- feature firewall fingerprint:
  `e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0`;
- cohort acceptance: `fl9-v2-cohort-acceptance-v1`;
- evidence floors: `fl9-v2-cohort-evidence-floor-v1`.

## 25. Authority boundary

This design authorizes no training.

Until the acceptance artifact is implemented, sealed, deployed, physically generated, and fingerprint-verified:

- cohort floor accepted: **NO**;
- eligible identity fingerprint created: **NO**;
- final V2 cohort artifact: **NOT CREATED**;
- final first-champion split authority: **BLOCKED**;
- target values inspected for this cohort: **NO**;
- model training: **BLOCKED**;
- model performance: **NOT INSPECTED**;
- PnL: **NOT INSPECTED**;
- PAPER promotion: **BLOCKED**;
- LIVE trading: **DISABLED**.
