# G1C V2 PAPER Evidence Manifest Authority — Design

**Date:** 2026-09-23  
**Status:** DESIGN FOR RED/GREEN IMPLEMENTATION  
**Scope:** Bind the Rust PAPER evidence collector to the authenticated G1C V2 campaign-manifest quote identity without mutating host configuration or weakening existing runtime authority.

## Production evidence

Protected PAPER rotation activated canonical V2 run:

- paper run: `g1c-v2-wsol-20260923T190847Z`
- manifest fingerprint: `bf73b9742aebc06ba12ba6e16d8810543a92a7a8476db6950534eb5dfe1f644d`
- quote mint: WSOL `So11111111111111111111111111111111111111112`
- entry input amount: `211545104`

The protected campaign service is healthy, but the separately supervised `shreks-paper-evidence` process remains configured from `/etc/shreks/shreks.env` with the legacy USDC quote mint and entry amount `25000000`.

Read-only production diagnostics proved:

- active V2 manifest quote mint = WSOL;
- environment-file quote mint = USDC;
- live evidence-process quote mint = USDC;
- active V2 entry amount = `211545104`;
- environment/live evidence-process entry amount = `25000000`;
- exact V2 ENTRY evidence rows after V2 start = `0`.

This is an authority mismatch between the authenticated campaign manifest and a second environment-driven PAPER evidence policy channel.

## Governing constraints

This slice must preserve:

- canonical campaign-manifest authentication in the existing Python decoder;
- legacy v1 PAPER evidence behavior;
- the existing Rust evidence collector and its provider/runtime semantics;
- release-manager process identity verification of the final Rust `shreks-paper-evidence` executable;
- protected manifest ownership/mode and rotation evidence;
- no direct host environment mutation;
- no scoring/model-fitting authority;
- no PAPER promotion authority;
- LIVE disabled.

The implementation must not:

- add a second V2 manifest decoder in Rust;
- hand-copy production WSOL economics into systemd or source constants;
- edit `/etc/shreks/shreks.env`;
- persist a new mutable derived policy artifact;
- weaken exact quote-identity matching in the PAPER campaign;
- infer or manufacture candidate economics.

## Design

Add a release-local Python launcher module:

`shreks_brain.paper_evidence_runtime_launcher`

The launcher runs as the `ExecStart` process for `shreks-paper-evidence.service`, authenticates the configured campaign manifest with the existing canonical Python decoder, derives the exact V2 evidence-collector quote policy, and then replaces itself with the existing Rust binary via `os.execve`.

Because the launcher uses `execve`, the final process visible to systemd and the release manager remains:

`/opt/shreks/current/target/release/shreks-paper-evidence`

No supervising Python process remains.

### V2 behavior

For canonical schema `g1c-paper-campaign-runtime-manifest-v2`, override only the child-process copies of these environment variables from authenticated manifest fields:

- `SHREKS_PAPER_QUOTE_ASSET_MINT` <- `policy_bundle.quote_asset.mint`
- `SHREKS_PAPER_ENTRY_INPUT_AMOUNT` <- `policy_bundle.entry_quote_identity.input_amount`
- `SHREKS_PAPER_EXIT_INPUT_AMOUNT` <- `policy_bundle.safety_probe_identity.input_amount`
- `SHREKS_PAPER_PROBE_POLICY_VERSION` <- `policy_bundle.entry_quote_identity.probe_policy_version`
- `SHREKS_PAPER_QUOTE_TAKER` <- `policy_bundle.entry_quote_identity.taker`
- `SHREKS_PAPER_SLIPPAGE_BPS` <- `policy_bundle.entry_quote_identity.slippage_bps`

The manifest's existing `ObserverFreshLaunchPolicyBundle` invariants already prove quote-asset, regime-read, entry-identity, and safety-probe consistency.

The host environment file remains unchanged. Provider credentials and unrelated collector controls remain environment-driven.

### V1 behavior

For canonical schema `g1c-paper-campaign-runtime-manifest-v1`, pass the existing environment through unchanged. This preserves the legacy collector policy path exactly.

### Fail-closed behavior

The launcher must not execute the Rust collector when:

- the manifest path is missing/blank;
- the manifest is not a real existing regular file;
- the manifest changes during the read;
- canonical manifest decoding/fingerprint verification fails;
- the Rust collector executable is unavailable.

Errors are sanitized and return nonzero through systemd's existing bounded restart/start-limit behavior.

## systemd integration

Change only `shreks-paper-evidence.service` startup:

from direct Rust execution to:

`/opt/shreks/current/.venv/bin/python -m shreks_brain.paper_evidence_runtime_launcher`

Also set `PYTHONDONTWRITEBYTECODE=1` so the immutable release remains write-free.

The launcher immediately `execve`s the release-local Rust binary, preserving the existing release-manager process identity checks.

## Verification

RED tests must prove the behavior is absent before implementation:

1. authenticated V2 manifest overrides stale quote-policy environment values;
2. canonical V1 manifest preserves environment values unchanged;
3. tampered V2 manifest fails closed and never reaches exec;
4. systemd routes PAPER evidence startup through the manifest-authority launcher and disables bytecode writes.

GREEN implementation must make those tests pass without changing campaign quote lookup semantics.

Full CI must remain green:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 immutable release build.

## Authority firewall

```text
PAPER_EVIDENCE_V2_QUOTE_AUTHORITY=AUTHENTICATED_CAMPAIGN_MANIFEST
HOST_ENV_POLICY_MUTATION=NOT_REQUIRED
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED_BY_THIS_SLICE
SCORING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
