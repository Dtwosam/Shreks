# FL1 Chainstack realtime fallback plan

## Context

FL1.5 production acceptance is blocked on realtime Pump/PumpSwap availability, not on host resources or SQLite integrity.

Two independent provider failures have now been proven on the production-paper host:

1. Helius primary returns HTTP 429 with `max usage reached`, proving the free project quota is exhausted.
2. The configured Alchemy Solana Mainnet app/key returns HTTP 200 for ordinary Solana RPC (`getVersion`, Solana core 4.2.1), but its WebSocket backend rejects the documented native Solana `logsSubscribe` request with JSON-RPC `-32601 Method 'logsSubscribe' not found`.

The current observer correctly fails closed when all configured realtime sources are unusable. FL2 therefore remains blocked and LIVE remains disabled.

## Decision

Add Chainstack as a realtime-only standard-Solana fallback between Helius and Alchemy:

1. Helius
2. Chainstack
3. Alchemy

Chainstack is selected because its current Solana WebSocket documentation explicitly demonstrates native `logsSubscribe` against the Pump.fun program, and its Developer tier is permanent/free with WebSocket access. Alchemy remains tertiary so its integration does not need to be removed if its PubSub routing later becomes usable.

## Secret boundary

Chainstack is configured by the complete host-only WebSocket endpoint:

```text
CHAINSTACK_SOLANA_WSS_URL=<full Chainstack Solana WSS endpoint>
```

The full endpoint is credential material. It must remain only in protected VPS runtime configuration and must never be committed, logged, copied into acceptance evidence, or pasted into ChatGPT/GitHub issues.

Provider configuration Debug output exposes enablement only and redacts endpoint contents.

## Runtime contract

- Chainstack is realtime-only; it receives no chain-state or transaction-RPC authority.
- One ordered `PumpRealtimeFailoverStream` remains the only production Pump/PumpSwap realtime source.
- The existing native Solana `logsSubscribe` request shape is reused unchanged.
- The active provider remains sticky after success.
- Retryable provider exhaustion rotates to the next configured provider.
- A complete pass with no working provider returns an error so observer supervision fails closed.
- No wallet, signing, execution, PAPER, LIVE, or FL2 authority changes.

## Provenance contract

Add stable provider identity:

```text
chainstack
```

That identity must survive:

- realtime notification parsing;
- Pump raw evidence writes/readback;
- PumpSwap raw evidence writes/readback;
- canonical FastEvent normalization/readback.

No Chainstack observation may be relabeled as Helius or Alchemy.

## TDD evidence

RED was captured on PR #85 at head `522a9a3c18857a38c69e6d709dc743edcffa1387`, CI run `33216787682`.

Repository safety passed and Rust failed specifically because `ProviderId::Chainstack` did not yet exist (`E0599`). The RED contract covers stable identity, host configuration/redaction, provider ordering, native WebSocket provenance, Helius-to-Chainstack failover, Pump/PumpSwap durable evidence, canonical provenance, and production architecture.

GREEN implementation is intentionally limited to satisfying that contract.

## Verification gate

Before merge, require exact-head PR CI to pass:

- Repository safety
- Rust tests
- Python tests
- ARM64 release build

After merge, require merged-main CI on the exact merge SHA. Then create a byte-identical `seal:` commit if necessary and require seal CI plus immutable release creation.

## Production acceptance

Do not run the full 15-minute FL1.5 interval immediately after deployment. First prove a short read-only sanity window:

- exact new sealed release executable is active;
- running process contains the Chainstack endpoint presence without exposing its value;
- Pump raw events > 0;
- PumpSwap raw events > 0;
- canonical events > 0;
- sequence integrity violations = 0;
- while Helius remains exhausted, provider counts contain `chainstack` progress;
- observer stays active without restart churn.

Only after that sanity pass should the representative FL1.5 acceptance interval run.

## Separate deployment correctness defect

The previous release deployment switched `/opt/shreks/current` but left the old observer process running, allowing an `is-active` health check to pass against stale code/config. This is a separate release-manager correctness defect. Future deployment health must prove the runtime process was actually replaced by the newly activated release rather than merely remaining active.

## Hold rule

Until physical-host FL1.5 passes with representative Pump and PumpSwap traffic, intact canonical progress, truthful provider provenance, and healthy supervision:

- FL2 remains blocked.
- LIVE TRADING remains disabled.
