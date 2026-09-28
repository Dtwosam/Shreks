# Fast Lane Authoritative PAPER Cutover Preparation — Design

**Date:** 2026-09-28  
**Base main SHA:** `8cd57f80208407c17c1a28666b3212ac9007c55f`

## Purpose

Prepare the already-built authoritative Fast Lane PAPER runtime for a protected
production cutover without changing the active service.

This slice seals the future replacement unit and deployment contract inside the
release wheel, then upgrades the read-only cutover preflight so a READY result
proves the authoritative Fast handoff is still pristine and exactly derived from
the final flat legacy PAPER checkpoint.

The active checkout remains:

```text
shreks-paper-campaign.service
-> shreks_brain.observer_campaign.runtime
```

The sealed candidate becomes:

```text
shreks-paper-campaign.fast-paper.service
-> shreks_brain.fast_paper_runtime.authoritative_runtime
```

Packaging the candidate is not service-control authority.

## Sealed commissioning assets

Every release wheel carries a separately fingerprinted package:

```text
shreks_brain/_sealed_fast_paper_authoritative_commissioning/
  manifest.json
  shreks-paper-campaign.fast-paper.service
  shreks-fast-paper-authoritative.env.example
```

The nested manifest binds exact release SHA, native platform, asset sizes and
SHA-256 fingerprints.

The candidate unit must use:

- `User=shreks`;
- `Group=shreks`;
- `/opt/shreks/current`;
- `/etc/shreks/fast-paper-authoritative.env`;
- `authoritative_runtime --preflight`;
- `authoritative_runtime`;
- `PrivateNetwork=true`;
- PAPER-only filesystem access.

It must not reference the shadow supervisor, legacy observer campaign runtime,
transaction signing/submission, or LIVE.

The current active `deploy/systemd/shreks-paper-campaign.service` is not
modified in this slice.

## Immutable authoritative environment

The protected production environment has a closed key set matching the
authoritative runtime introduced in PR #652.

Static production roots are exact:

```text
/etc/shreks/fast-paper-runtime-manifest.json
/etc/shreks/fast-paper-shadow-service-policy.json
/etc/shreks/fast-paper-shadow-execution-policy.json

/var/lib/shreks/fast-paper-authoritative/decision
/var/lib/shreks/fast-paper-authoritative/decision/runtime-state.json
/var/lib/shreks/fast-paper-authoritative/execution-sources
/var/lib/shreks/fast-paper-authoritative/buy-authority-sources
/var/lib/shreks/fast-paper-authoritative/quote-usd-sources
/var/lib/shreks/fast-paper-authoritative/reduction-sources
/var/lib/shreks/fast-paper-authoritative/pending-buy-retry-sources
```

The authoritative runtime owns a dedicated learned-decision evidence directory and checkpoint path. The cutover ceremony must seed that checkpoint from the exact latest authenticated detached-shadow decision state after the shadow is quiesced. Production decision evidence must still be empty at the cutover gate.

The authoritative database path is not guessed. It must exactly equal the
observer database path sealed in the Fast runtime manifest and the legacy
observer database supplied to cutover preflight.

The Fast authoritative run ID must be explicit non-placeholder text.

The initial protected cadence is fixed at 2 seconds and the runtime itself
hard-bounds learned decision production to one row per cycle.

## Upgraded cutover preflight

`shreks-fast-paper-cutover-preflight` additionally requires:

- `--authoritative-runtime-env-path`;
- `--authoritative-release-wheel-path`;
- `--release-platform`.

Before a READY decision, preflight authenticates:

1. exact Fast manifest/champion identity;
2. detached learned-shadow restart proof;
3. current isolated shadow accounting proof;
4. exact sealed authoritative commissioning package in the release wheel;
5. exact authoritative runtime env/source roots;
6. authoritative runtime bootstrap against the persisted binding/checkpoint;
7. final legacy PAPER checkpoint/accounting and flatness.

## Pristine handoff gate

The authoritative Fast namespace must still be a non-executed handoff.

READY requires:

```text
authoritative_checkpoint_sequence=0
authoritative_pending_buy=0
authoritative_open_positions=0
authoritative_learned_execution_cursor=EMPTY
authoritative_decision_baseline=MATCHES_LATEST_SHADOW_CURSOR
authoritative_decision_evidence=EMPTY
authoritative_accounting=RECONCILED
```

The learned decision cursor may already be advanced from shadow operation. That history is not replayed economically. Instead, the production decision checkpoint must exactly equal the latest authenticated shadow decision state, and the authoritative coordinator treats that cursor as the non-economic source baseline until the first new production decision commits. If a crash occurs after the first new decision evidence is written but before its economic commit, the dedicated production evidence file reconstructs the one-step cursor gap on restart.

The persisted authoritative binding must reference the exact latest legacy:

- run ID;
- checkpoint sequence;
- checkpoint payload SHA;
- legacy runtime-manifest fingerprint.

The Fast checkpoint's `PaperLedger` must equal the final legacy checkpoint's
ledger exactly.

This prevents a stale handoff from being accepted after the legacy service has
advanced, and prevents any pre-cutover Fast economic execution from being
silently accepted.

## Report authority

A ready report now states:

```text
production_fast_paper_runner=SEALED_NOT_ACTIVE
production_paper_cutover=NOT_GRANTED
service_control_authority=NOT_GRANTED
authoritative_paper_mutation=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

The report binds the authoritative commissioning manifest fingerprint,
canonical env fingerprint, Fast run/binding identity, checkpoint fingerprint,
runtime-state fingerprint, and all legacy/handoff gates.

## Authority firewall

This slice must not:

- stop/start/restart/reload systemd;
- overwrite the active PAPER unit;
- invoke learned economic actions;
- write a PAPER checkpoint;
- initialize a handoff;
- change the champion;
- fetch provider/network facts;
- sign or submit transactions;
- enable LIVE.

## Acceptance proof

Tests must prove:

1. the authoritative candidate unit/env are sealed into release wheels;
2. active legacy unit bytes remain unchanged;
3. candidate unit points only to the authoritative Fast PAPER entrypoint;
4. production env parsing is closed and rejects shell syntax/drift;
5. authoritative DB must equal manifest/legacy observer DB;
6. placeholder Fast run IDs are rejected;
7. cutover READY requires authoritative checkpoint sequence 0;
8. READY requires no authoritative pending BUY/open position/learned execution cursor;
9. the dedicated authoritative decision baseline must exactly match the latest authenticated shadow decision state;
10. authoritative production decision evidence must be empty before cutover;
11. authoritative binding must match the exact final legacy checkpoint;
12. authoritative ledger must equal the unchanged final legacy ledger;
13. Fast, legacy, and shadow accounting gates remain reconciled;
14. Python, Rust, ARM64, and repository-safety CI remain green.

## Following slice

The physical cutover is **not** next yet. Repository inspection shows the
authoritative BUY/reduction/pending-retry formats currently have builders and
readers, but no continuous production writer/publisher topology equivalent to
the proven shadow supervisor source writers.

The next slice must therefore (a) add the protected provisioning operation that
copies the exact authenticated shadow decision checkpoint into the already
implemented dedicated authoritative decision baseline only after the detached
shadow is quiesced, and (b) adapt the existing persisted-evidence authority
writers to the authoritative checkpoint/runtime pair. It must preserve the
restart-safe first-decision continuation proved here while adding continuous
BUY/HOLD/REDUCE/SELL and pending-BUY retry source production without shadow
ledger mutation.

After that, protected host preparation may install the exact authoritative env
and create the dedicated source directories. Only the final cutover ceremony
may stop the legacy PAPER campaign and detached shadow services, re-run this
preflight against the newly final legacy checkpoint, replace the active unit,
daemon-reload, and start Fast PAPER authority.

LIVE remains disabled.
