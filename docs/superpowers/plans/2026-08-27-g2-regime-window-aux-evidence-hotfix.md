# G2 aggregate regime auxiliary-evidence production hotfix

Date: 2026-08-27

## Production evidence

The sealed PAPER release `90acd5927c826b8476cfc513c06a2fad34feaae6` deployed successfully to the ARM64 VPS and passed G1C runtime preflight, but the running campaign failed after the first completed cycle once real observer candidates and Helius/Jupiter auxiliary evidence became available.

A read-only physical-host diagnostic reproduced the underlying exception without advancing PAPER state:

```text
ObserverCampaignCoordinatorError: observer candidate 49 assembly failed: observer paper cycle assembly failed: aggregate regime consumed evidence is not inside the requested window
ObserverPaperAssemblyError: observer paper cycle assembly failed: aggregate regime consumed evidence is not inside the requested window
ObserverCampaignReadError: aggregate regime consumed evidence is not inside the requested window
```

The evidence collector itself was healthy and stored holder plus entry/exit quote evidence for two real candidates with zero provider failures. The runtime failure was therefore isolated to aggregate regime replay semantics rather than provider transport, release transport, systemd bootstrap, or the campaign manifest.

## Root cause

`ObserverCampaignStore.build_regime_market_window()` correctly bounded market snapshots to the requested regime window. However, the latest matching safety evidence and entry PAPER quote were loaded only with an upper point-in-time bound (`<= as_of_unix_ms`). Their timestamps were then unconditionally included in aggregate `consumed_timestamps`.

When an otherwise fresh candidate had auxiliary evidence older than `window_started_at`, the final fail-closed provenance invariant rejected the entire aggregate regime window:

```text
aggregate regime consumed evidence is not inside the requested window
```

## TDD proof

RED commit:

- `4ad38ee1a0250702d320b12d7a04282f208b0fdd`
- added `python/tests/test_g2_regime_window_aux_evidence.py`
- CI run `33077274704`
- Python result: exactly `1 failed, 2617 passed`
- failure was the same `ObserverCampaignReadError` observed on the VPS

GREEN commit:

- `4f74b74d56030c488633cc5c28b2074fdc9cbedc`
- stale safety provenance is not consumed by the aggregate regime window
- stale entry-quote provenance is not consumed by the aggregate regime window
- stale safety or entry-quote evidence cannot make a candidate executable
- the final aggregate window provenance invariant remains unchanged

Final PR CI:

- run `33077916524`
- Repository safety: GREEN
- Python: GREEN, `2618 passed`
- Rust: GREEN
- native ARM64 release build: GREEN

PR #57 was squash merged as behavior commit:

- `d90b17b9916d3af283dea8a261bb2a1af2998da0`

## Invariants preserved

This hotfix does not change strategy thresholds, risk thresholds, PAPER campaign economics, provider credentials, systemd semantics, release-manager semantics, wallet/signing authority, or LIVE capability.

Missing/stale auxiliary evidence remains fail-closed for the affected candidate. The change only prevents evidence outside the requested aggregate regime window from poisoning the provenance of otherwise fresh evidence inside that window.

LIVE remains disabled.
