# Phase G1C Paper Campaign Runtime Bootstrap — Design

**Date:** 2026-08-25  
**Base:** sealed G1B `ad1a6527e6cb312af53b16e70b8f0cd26eda47a9`  
**Purpose:** bind the sealed G1B multi-token PAPER coordinator to one immutable, reproducible runtime configuration artifact and one supervised Python process without hard-coding strategy/risk/economic policy into the daemon.

## Boundary

G1C is PAPER-only runtime bootstrap. It does not add registry mutation, promotion, live execution, transaction construction, signing, submission, wallet authority, or trading-provider credentials.

The runtime process may read the observer SQLite database and durable paper evidence/checkpoint state already authorized by sealed components. It must consume explicit immutable startup configuration rather than inventing strategy/risk/economic thresholds in environment variables or daemon code.

## Configuration artifact

G1C introduces one versioned JSON campaign manifest that fully describes the startup objects required by the sealed coordinator:

- paper run ID;
- immutable `RegistryCandidate` attribution;
- initial paper ledger/loop/fill state;
- `ObserverFreshLaunchPolicyBundle` including market/safety/regime/setup/score/decision/risk/exit and quote identities;
- `ObserverPaperRiskEnvironment`;
- `ObserverPaperCampaignSelectionPolicy`;
- optional recent strategy performance;
- global risk halt flag.

The manifest is configuration/proof input, not mutable runtime state. It must be canonical, schema-versioned, validation-heavy, and fingerprinted. Unknown/missing keys fail closed. Decoding must reconstruct exact sealed domain types; no defaults may silently supply trading thresholds.

Operational paths and cadence remain separate runtime configuration because they are deployment/environment concerns rather than trading-policy content:

- observer SQLite path;
- E11 evidence path;
- campaign manifest path;
- cycle interval;
- optional finite cycle limit for controlled verification.

## Runtime entrypoint

A Python module entrypoint runs one `ObserverPaperCampaignCoordinatorRunner` continuously in PAPER mode:

1. load and validate operational runtime config;
2. load/decode the immutable campaign manifest;
3. construct the sealed G1B coordinator runner;
4. restore existing checkpoint/E11 state before work;
5. on each cycle, derive one wall-clock millisecond timestamp;
6. invoke exactly one aggregate PAPER cycle;
7. emit structured status only after the sealed runner completes persistence/restart validation;
8. sleep according to explicit operational cadence;
9. stop cleanly on SIGINT/SIGTERM.

The daemon must not derive token candidates itself, score outside G1B, mutate the registry, or call any live execution surface.

## Restart and initial-state rules

The manifest carries an explicit initial paper state only for a new paper run. If durable C6 state exists for the same run, the sealed runner restores it. Existing E11 attribution must remain coherent with the manifest candidate. A manifest change that conflicts with stored run attribution fails closed.

A normal process restart therefore resumes from durable evidence/checkpoint state rather than resetting paper capital, pending intent, or positions.

## Supervision

G1C wires the Python paper campaign into the existing G1 systemd deployment model with a dedicated service unit. Persistent database/evidence/manifest paths live outside the release checkout. The service:

- runs as the non-root Shreks service user;
- loads operational paths/cadence from the shared environment file;
- restarts on failure;
- uses SIGINT/SIGTERM-compatible shutdown;
- carries no wallet key or live-mode flag.

## Fail-closed behavior

Startup/cycle processing fails rather than guessing when:

- manifest bytes are invalid/non-canonical or fingerprint/schema checks fail;
- any reconstructed policy/domain object is invalid;
- operational paths/cadence are malformed;
- observer/evidence/checkpoint state is contradictory;
- G1B selection/assembly/runner fails;
- accounting/restart equivalence fails.

No fallback strategy values, starting capital, risk thresholds, slippage assumptions, or selection bounds are embedded in the daemon.

## Proof standard

G1C proves reproducible bootstrap and unattended PAPER process mechanics. It does not prove profitability. After G1C is sealed and deployed, the next objective is to run an actual point-in-time paper campaign long enough to generate independent real trades and evaluate them through E10/E11/E12.

**LIVE TRADING REMAINS DISABLED.**
