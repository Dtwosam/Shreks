# Fast PAPER Shadow BUY Writer Deployment Policy + Supervisor Wiring — Design

**Date:** 2026-09-27  
**Base main SHA:** `0e5a2daee4ceb867a089dd43d7f376a7ca7a3957`

## Purpose

Complete the supervised learned-shadow BUY authority path without introducing
runtime defaults or reusing the legacy scoring control path.

The restart-safe BUY-authority writer already composes persisted point-in-time
evidence and can publish the authenticated BUY-authority record. The supervised
daemon still does not have authenticated deployment authority for the writer's
market/regime/safety/economics/control inputs.

Add one fingerprinted, score-free deployment policy artifact and wire the writer
immediately before the existing BUY execution-source publisher.

## Policy schema

Add:

`shreks.fast_paper_shadow_buy_writer_policy` version `1`.

Public API:

- `FastPaperShadowBuyWriterPolicy`;
- `build_fast_paper_shadow_buy_writer_policy(...)`;
- `read_fast_paper_shadow_buy_writer_policy(...)`;
- `write_fast_paper_shadow_buy_writer_policy(...)`;
- `verify_fast_paper_shadow_buy_writer_policy_bindings(...)`.

The artifact contains only:

- exact `ObserverMarketReadPolicy`;
- exact `ObserverRegimeReadPolicy`;
- exact `RegimePolicy`;
- exact `SafetyPolicy`;
- exact `ObserverSafetyProbeIdentity`;
- exact full-horizon tuple of
  `FastDeterministicComparisonExecutionPolicy`;
- absolute operator risk-control state path;
- absolute release-local FL3 entry-authority binary path;
- SHA-256 of that FL3 binary;
- explicit risk-day start;
- explicit data-health fact (`bool | None`);
- explicit execution-health fact (`bool | None`);
- explicit global-risk-halt fact;
- deterministic policy fingerprint.

It must contain no score policy, decision threshold, trading recommendation,
provider credential, signer, wallet, or LIVE field.

## Canonical persistence

The policy is canonical JSON with exactly one trailing newline.

The reader/writer must fail closed on:

- unknown/missing fields;
- duplicate JSON keys;
- non-finite JSON;
- malformed nested policy fields;
- fingerprint mismatch;
- non-canonical payload;
- symlink source/destination;
- overwrite attempts.

New files use mode `0600`.

## Runtime bindings

`verify_fast_paper_shadow_buy_writer_policy_bindings(...)` binds the policy to
the active Fast PAPER runtime manifest and shadow service policy.

Require:

- runtime quote provider remains Jupiter;
- regime ENTRY identity exactly matches service probe version, quote mint,
  ENTRY amount, taker, and slippage;
- safety EXIT identity exactly matches service probe version, quote mint,
  EXIT amount, taker, and slippage;
- execution-economics horizons exactly cover
  `manifest.action_policy.horizons_ms`;
- entry-authority binary is a regular non-symlink file;
- binary SHA-256 equals the sealed policy digest;
- binary lives beside the active learned decision binary in the same
  release-local binary directory;
- operator risk-control state is a regular non-symlink file.

No network lookup or provider call is allowed during verification.

## Supervisor configuration

Require environment setting:

`SHREKS_FAST_PAPER_SHADOW_BUY_WRITER_POLICY_PATH`.

Add the absolute path to `FastPaperShadowSupervisorConfig`.

Supervisor bootstrap must:

1. authenticate decision bootstrap;
2. authenticate execution bootstrap;
3. read and authenticate the BUY-writer policy;
4. verify all BUY-writer policy/runtime/service bindings;
5. validate existing source roots.

The authenticated policy is retained in
`FastPaperShadowSupervisorBootstrap`; the cycle does not re-read or invent
settings.

## Cycle ordering

The supervised cycle order becomes:

1. SKIP execution-source publisher;
2. BUY-authority writer;
3. BUY execution-source publisher;
4. OPEN execution-source publisher;
5. coordinator / execution / next decision.

The BUY-authority writer receives only the authenticated retained policy fields
plus the exact current decision/execution bootstraps and source directories.

This means a learned BUY can flow:

`decision -> BUY authority -> BUY execution source -> isolated PAPER executor`

within the same supervised cycle when all exact prerequisite evidence already
exists.

## Provisioning and deployment

The provisioner does not create or mutate the policy artifact. It only requires
the configured path through supervisor configuration.

The packaged environment example must expose the policy path, for example:

`/etc/shreks/fast-paper-shadow-buy-writer-policy.json`.

## Authority boundary

```text
BUY_WRITER_DEPLOYMENT_POLICY=FINGERPRINTED_EXPLICIT_ONLY
RUNTIME_DEFAULTS=FORBIDDEN
MULTI_HORIZON_ECONOMICS=EXACT_ACTION_POLICY_COVERAGE
OPERATOR_CONTROL=READ_ONLY_EXISTING_STATE
BUY_AUTHORITY_WRITE=EXISTING_WRITER_ONLY
BUY_EXECUTION_SOURCE=EXISTING_PUBLISHER_ONLY
PAPER_EXECUTION=EXISTING_ISOLATED_EXECUTOR_ONLY
PROVIDER_NETWORK_ACCESS=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
LIVE=DISABLED
```

## RED acceptance

Intentional RED tests require:

- stable public policy schema/build/read/write/verify API;
- canonical private round trip and tamper refusal;
- exact service/runtime identity binding;
- exact full learned-horizon economics coverage;
- FL3 binary path/hash/release-directory verification;
- operator-control path verification;
- required supervisor environment path;
- policy retained in supervisor bootstrap;
- exact SKIP -> BUY-authority-writer -> BUY-source -> OPEN -> coordinator order;
- exact policy field forwarding into the writer;
- packaged environment example coverage;
- no scoring, provider-network, execution implementation, signing, or LIVE
  authority.

Current main is expected to fail during Python collection because the new policy
module/public API does not exist.

## Following slice

Run the supervised path against a provisioned isolated PAPER shadow environment
with real persisted observer/quote/USD evidence and prove the first learned BUY
can move end-to-end from decision evidence to an isolated PAPER ledger position
without authoritative PAPER cutover or LIVE authority.
