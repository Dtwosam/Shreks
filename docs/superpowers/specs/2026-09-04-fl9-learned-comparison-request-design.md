# FL9 Learned Comparison Request — Design

**Date:** 2026-09-04

## Status

Implementation slice after the learned-vs-baseline comparison proof artifact merged as
`6ed40f89d6bf55bbda534d9e1de64cdc99a1002f` (#198).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Purpose

Provide one canonical file-backed request that turns the already authenticated deterministic
comparison campaign into the learned-candidate comparison proof without creating a second
market-evidence path.

The request is orchestration evidence. It does not collect provider data, invent execution
economics, or change the sealed baseline campaign.

## Request schema

Schema:

`shreks.fast_learned_comparison_request` v1.

The canonical request binds:

- baseline invocation path;
- exact FL8.5 champion file path;
- learned Rust decision-binary path and SHA-256;
- proof destination path;
- learned PAPER run id;
- learned candidate/strategy/assessment identity;
- exact `FastCampaignContinuousActionPolicy`;
- one ordered explicit row-input binding per baseline source event;
- exact `FastPolicySuperiorityPolicy`;
- canonical request fingerprint.

Floating-point action-policy, constraint, reduction-cost, and entry-authority values use exact
hexadecimal float text inside the request codec. The nested superiority policy uses the existing
authenticated #198 policy codec.

Unknown/missing fields, non-canonical JSON, malformed values, duplicate source-event ids, and
fingerprint mismatches fail closed.

## Row-input contract

Each `FastLearnedComparisonRowInput` carries:

- exact `source_event_id`;
- explicit FLAT `FastCampaignActionConstraints`;
- explicit OPEN `FastCampaignActionConstraints`;
- optional learned-candidate `FastCampaignPaperEntryAuthority`.

The constraints remain explicit evidence, matching the sealed learned chronological PAPER
design. The orchestrator does not calculate or infer execution economics.

The entry authority is candidate-specific because intended quantity and acceptable entry bounds
belong to the learned candidate. When present, its mint, quote mint, and decision executable entry
price must match the authenticated FL8.1 row.

## Baseline authority

Execution begins by strict-reading the existing deterministic campaign invocation seal and its
bound campaign artifact.

The request runner inherits from the sealed deterministic request:

- starting PAPER cash;
- starting PAPER ledger timestamp;
- fill policy;
- risk policy;
- position policy;
- trading-evaluation policy.

Those values are not duplicated in the learned request. This prevents an apparently same-population
comparison from silently changing PAPER or evaluation semantics.

## Same-population evidence

The learned runner is fed from the deterministic campaign's immutable comparison bundle.

For every row, request order and `source_event_id` must exactly match:

`decision_signature:decision_ordinal`.

The learned row reuses the baseline bundle's exact:

- `FastTrainingFeatureRecord`;
- state version and evaluation timestamp;
- directional ENTRY/EXIT quote evidence;
- market regime;
- dynamic risk environment.

Only the learned candidate's explicit FLAT/OPEN constraints and optional entry authority come from
this request.

Population mismatch fails before learned Rust execution.

After the learned PAPER run, its event-population fingerprint must equal the deterministic campaign
manifest's event-population fingerprint before the proof artifact may be written.

## Source authentication

The learned Rust decision binary is content-authenticated by SHA-256 in the request.

The champion file is independently hashed and required to equal the champion source fingerprint
stored in the authenticated deterministic invocation.

Both files are re-authenticated after learned execution. The canonical learned request file must
also remain byte-identical during execution.

The deterministic invocation is strict-read again before proof publication and its manifest must
remain unchanged.

## Learned execution

After all preflight gates:

1. build the learned candidate identity from the authenticated champion and exact action policy;
2. create the starting PAPER ledger from the sealed baseline request;
3. run the existing `run_fast_learned_chronological_campaign(...)`;
4. require exact learned/baseline event-population fingerprint equality;
5. call the existing #198 `write_fast_policy_comparison_artifact(...)`;
6. strict-read and return the resulting proof artifact.

The #197 learned chronological driver remains responsible for state-aware Rust prefix decisions,
actual PAPER posture reconstruction, chronology/leakage gates, and action-compatible PAPER evidence.

The #198 proof artifact remains responsible for exact eight-baseline coverage, immutable publication,
child authentication, and superiority-report recomputation on read.

## Economic truth

This request does not force a profitable result.

Once integrity and population parity are valid, the proof artifact may truthfully record:

- `SUPERIOR`;
- `FAILED`;
- `INSUFFICIENT_EVIDENCE`.

A losing learned candidate is useful evidence and must not be hidden or rewritten.

## Failure behavior

Fail before the next economic step on:

- malformed/non-canonical request;
- request fingerprint mismatch;
- invalid or changed decision binary;
- champion content not matching the sealed baseline source;
- baseline invocation/campaign fingerprint mismatch;
- request/baseline source-event population mismatch;
- learned entry-authority market/price provenance mismatch;
- learned/baseline event-population fingerprint mismatch;
- request, champion, binary, or baseline invocation changing during execution;
- invalid proof destination relationship;
- any downstream sealed learned/proof invariant failure.

No partially published proof directory is accepted.

## Authority boundary

This slice does not:

- collect provider/network data;
- query operational storage;
- choose a strategy or model;
- alter the baseline campaign;
- sign or submit transactions;
- enable LIVE;
- change runtime service topology.

It is authenticated offline/PAPER comparison orchestration only.

## TDD provenance

Intentional RED:

- `a9e7eebc66bd2d63ae30fe0aade87259b5129071` — request/runner API absent.

The RED was isolated to Python import/collection for the missing new API while repository safety
and ARM64 remained green.

Implementation tests cover:

- canonical authenticated request round-trip and tamper rejection;
- exact source-event population gate before learned launch;
- decision-binary and sealed-champion authentication before learned launch;
- reuse of baseline row evidence and exact baseline PAPER/evaluation policies;
- proof-writer handoff;
- authority firewall.

## Following work

After this slice is sealed, the proof plumbing required by the #198 plan is complete.

The next task is not another synthetic proof layer. It is to locate or produce the real non-fixture
runtime inputs required by the authenticated request and execute the first genuine FL9 learned-vs-
baseline evidence campaign.

That economic result must be accepted as measured: superior, failed, or insufficient.
