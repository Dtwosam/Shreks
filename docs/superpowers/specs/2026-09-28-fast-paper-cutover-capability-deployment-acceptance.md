# Fast PAPER Cutover-Capability Deployment Acceptance

**Date:** 2026-09-28  
**Cutover implementation main:** `0f4f6c90b8d8cc2a3e6d303eeb1e04b5f12d102f`  
**Release seal main:** `cbb2f64e7e79cfffc3db6366915963a441f6d2b5`  
**Immutable release:** `shreks-cbb2f64e7e79cfffc3db6366915963a441f6d2b5`  
**Release workflow:** `36479712857`  
**Protected deploy workflow:** `36480537279`  
**Status:** CUTOVER CAPABILITY DEPLOYED; LEGACY PAPER STILL AUTHORITATIVE; PHYSICAL CUTOVER NOT YET EXECUTED; LIVE DISABLED

## Purpose

Record the exact physical-host state after deploying the sealed Fast PAPER
physical-cutover capability and distinguish release/service acceptance from the
separate legacy G1C mint-state behavioral acceptance gate.

This record does not claim that the failed reusable production verifier passed.

It records why that verifier failure is not evidence of a cutover-code,
release-identity, service-health, accounting-handoff, or Fast-runtime defect,
and it preserves the dedicated physical-cutover preflight as the mandatory
authority-switch gate.

## Immutable release proof

The automatic sealed-release workflow succeeded for exact source:

`cbb2f64e7e79cfffc3db6366915963a441f6d2b5`

The published GitHub release is:

`shreks-cbb2f64e7e79cfffc3db6366915963a441f6d2b5`

The release object is:

- immutable;
- non-draft;
- non-prerelease;
- targeted at the exact seal SHA;
- limited to the expected three release assets.

The protected deploy workflow resolved and authenticated that exact immutable
release, downloaded and locally re-verified its assets, transferred them to the
protected host, and successfully invoked the existing narrow release manager.

## Physical host state proved before verifier failure

The deployed host reported:

```text
current_release=/opt/shreks/releases/cbb2f64e7e79cfffc3db6366915963a441f6d2b5
manifest_source_sha=cbb2f64e7e79cfffc3db6366915963a441f6d2b5
```

The protected manifest-manager helper matched the exact current release:

```text
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
```

All three ordinary PAPER services were active with:

```text
NRestarts=0
ExecMainStatus=0
```

The active campaign process remained the intended legacy authority:

```text
python -m shreks_brain.observer_campaign.runtime
```

The deployment therefore did not execute the Fast physical cutover.

Recent service journals also reported:

```text
observer_invalid_response_lines=0
recent_failure_signatures=none
```

## Reusable verifier failure

The reusable production verifier then returned terminal legacy G1C mint-state
physical acceptance `FAILED`.

Its bounded evidence was:

```text
g1c_v2_mint_state_selected_observations=2
g1c_v2_mint_state_proactive_refreshes=0
g1c_v2_mint_state_missing_selected=1
g1c_v2_mint_state_missing_later_observed=1
g1c_v2_mint_state_missing_unresolved=0
g1c_v2_mint_state_stale_selected=0
g1c_v2_mint_state_invalid_observations=0
g1c_v2_mint_state_reconstructed_checkpoints=1
g1c_v2_mint_state_max_selected_age_ms=75543
g1c_v2_mint_state_max_missing_followup_delay_ms=51624
g1c_v2_paper_evidence_completed_cycles=4
g1c_v2_paper_evidence_provider_failures_last_cycle=0
g1c_v2_helius_requests_attempted=16
g1c_v2_helius_requests_limit=500
g1c_v2_helius_requests_remaining=484
g1c_v2_helius_budget_exhausted=false
g1c_v2_mint_state_physical_acceptance=FAILED
```

The existing G1C acceptance contract intentionally reports `FAILED` whenever
any selected observation lacked mint state at its exact decision time. A later
successful Helius observation does not retroactively change that decision-time
fact.

That contract remains unchanged.

## Last accepted G1C physical gate

The last exact-release production PASS remains release:

`816e7c6591d216369b60f893cc5dfe5785e88652`

Protected verifier run:

`36178349929`

It proved:

```text
g1c_v2_mint_state_physical_acceptance=PASS
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
fl9_v2_discovery_status=FOUND_COMPATIBLE
```

A repository comparison from that accepted release through the current cutover
seal shows no changes to:

- `python/src/shreks_brain/observer_campaign/**`;
- the PAPER-evidence runtime implementation;
- `python/src/shreks_brain/telemetry/g1c_v2_mint_state_acceptance.py`;
- `.github/workflows/verify-production-paper.yml`.

Within the relevant service files, the only change is the newly added sealed
Fast PAPER candidate unit.

Therefore this deployment did not introduce a new legacy mint-state behavior or
weaken the legacy gate.

## Cutover acceptance boundary

The legacy G1C mint-state gate remains meaningful for continued operation of the
legacy score-gated campaign. This record does not convert its `FAILED` result
into `PASS`.

The physical Fast PAPER authority switch has a different safety question:
whether the exact final legacy economic state can be handed off without
duplication, loss, stale authority, or unresolved economic work.

The protected physical-cutover ceremony must therefore still fail closed unless
its own final stopped-legacy preflight proves all of the following:

- exact sealed release/process identity;
- exact final legacy checkpoint;
- legacy accounting `RECONCILED`;
- zero legacy open positions;
- zero legacy pending entries;
- zero legacy deferred exits/executions;
- zero active legacy intents;
- exact final Fast sequence-0 ledger equality to the final legacy ledger;
- authoritative Fast accounting `RECONCILED`;
- no prior Fast economic execution;
- no Fast pending BUY;
- no Fast mapped open position;
- exact learned decision baseline;
- explicit final Fast run namespace;
- exact cutover authorization;
- LIVE disabled;
- signing/submission authority not granted.

A transient legacy mint-state miss does not bypass any of those economic
handoff gates.

## Operational consequence

The exact cutover-capable release is physically deployed.

The next authority-changing action remains the trusted-administrator physical
cutover ceremony.

Before that ceremony:

```text
production_paper_runtime=LEGACY
production_paper_cutover=NOT_ACTIVE
fast_cutover_capability=DEPLOYED
signing_submission_authority=NOT_GRANTED
LIVE=DISABLED
```

Only a successful physical-cutover receipt may change this to:

```text
production_paper_runtime=FAST_LANE_LEARNED
production_paper_cutover=ACTIVE
signing_submission_authority=NOT_GRANTED
LIVE=DISABLED
```

## Non-authority

This evidence record does not:

- alter the G1C mint-state acceptance algorithm;
- reinterpret `FAILED` as `PASS`;
- relax mint freshness or provider rules;
- change PAPER strategy/setup/scoring/risk policy;
- create a final Fast run;
- issue cutover authorization;
- stop or replace the legacy PAPER service;
- execute a Fast learned PAPER action;
- sign or submit transactions;
- enable LIVE.
