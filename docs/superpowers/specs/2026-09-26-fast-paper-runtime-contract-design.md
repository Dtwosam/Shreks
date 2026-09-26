# Fast Lane PAPER Runtime Contract — Design

**Date:** 2026-09-26  
**Base main SHA:** `fd71dd69aa7c496d84ee7eaf5f3d71d573488f64`  
**Migration plan:** `docs/superpowers/plans/2026-09-26-fast-lane-learned-paper-runtime-migration.md`

## Goal

Create the first production-facing contract for the learned Fast Lane PAPER runtime
without changing the active systemd service or mutating any PAPER ledger.

This slice defines:

- one immutable, score-free runtime manifest;
- one deterministic runtime cursor-state artifact;
- exact champion/binary identity verification;
- canonical codecs and safe file publication;
- an authority firewall that forbids the legacy scoring/entry-decision path.

No runtime event loop, observer feed, PAPER trade execution, service switch, model
training, champion promotion, or LIVE behavior is added here.

## Manifest contract

Schema:

`shreks.fast_paper_runtime_manifest` version 1.

The manifest binds:

- exact 40-char release source SHA;
- runtime mode fixed to `PAPER`;
- exact champion path, version, semantic fingerprint, and file SHA-256;
- exact executable Rust decision-binary path and SHA-256;
- exact `FastCampaignContinuousActionPolicy`;
- exact champion feature-schema version;
- exact Fast Lane state version;
- exact Fast PAPER event-loop version;
- risk, fill, and position-action policy versions;
- strategy family/version and action-assessment version;
- absolute observer database, PAPER evidence, and runtime-state paths;
- quote provider/mint/decimals and route-evidence version;
- deterministic manifest fingerprint.

The builder derives champion identity from the champion file rather than accepting
caller-supplied champion version/fingerprint values.

The decision binary must be a regular non-symlink executable.

## Runtime state contract

Schema:

`shreks.fast_paper_runtime_state` version 1.

State binds:

- runtime-manifest fingerprint;
- release source SHA;
- champion fingerprint;
- action-policy version;
- optional last processed decision cursor:
  - decision sequence;
  - source event ID;
  - decision observed timestamp;
- deterministic state fingerprint.

This state is only an input-feed/runtime identity cursor. It is **not** the
authoritative `PaperLedger`, and it grants no economic execution authority.

Manifest publication is write-once. Runtime state publication uses deterministic
canonical JSON and atomic replace so later feed slices can advance the cursor
without partial files.

## Binding verification

`verify_fast_paper_runtime_bindings(...)` re-reads:

- the champion file and verifies its semantic fingerprint/version/feature schema
  plus exact file SHA;
- the decision binary and verifies non-symlink regular executable identity plus
  exact SHA.

A changed champion or binary fails closed before later runtime work can proceed.

## No-scoring authority firewall

Production source in `shreks_brain.fast_paper_runtime` must not import or
reference:

- `shreks_brain.scoring`;
- `score_candidate`;
- legacy `shreks_brain.decision` entry logic;
- `decide_entry`;
- `ScorePolicy` / legacy `DecisionPolicy`;
- total-score threshold reason codes or required score thresholds.

The manifest cannot encode score fields because decoding requires an exact key
set.

Expected-net-value action floors in `FastCampaignContinuousActionPolicy` remain
valid Fast Lane economics; they are not token-quality scoring authority.

## Publication semantics

Manifest:

- canonical JSON plus trailing newline;
- mode 0600;
- destination must not already exist or be a symlink.

Runtime state:

- canonical JSON plus trailing newline;
- mode 0600;
- atomic temp-file + `os.replace`;
- destination symlinks are rejected.

## Non-authority

```text
ACTIVE_SYSTEMD_PAPER_RUNTIME=UNCHANGED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
FAST_LANE_EVENT_FEED=NOT_IMPLEMENTED
FAST_LANE_PAPER_EXECUTION=NOT_GRANTED
CHALLENGER_TRAINING=NOT_CHANGED
CHAMPION_PROMOTION=BLOCKED
SCORING_CONTROL_PATH=FORBIDDEN
LIVE=DISABLED
```
