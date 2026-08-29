# FL1 Chainstack Read-Only RPC Coverage

**Date:** 2026-08-29  
**Status:** implementation under CI; physical-host FL1.5 acceptance still required  
**LIVE TRADING:** DISABLED

## Why this change exists

Physical-host FL1.5 evidence on sealed release `f8c7b584cc7dc18d338d6f7ee264c74817228bbc` proved that Chainstack realtime ingestion continued while canonical FastEvent production remained starved.

The exact maximum normalizer frontier contained 8,192 pending rows and zero ready rows:

- Pump rows: 601
- PumpSwap rows: 7,591
- missing verified PumpSwap market mappings: 7,262
- missing verified base decimals: 921
- missing verified quote decimals: 9
- contradictory provider/market/decimal evidence: 0

The normalizer therefore had no eligible input. The blocker was upstream verification/enrichment rather than scan ordering or SQLite lookup performance.

The deployed observe runtime used Helius as its only chain-data and transaction-verification provider. Helius quota exhaustion could therefore stop the standard Solana `getAccountInfo` and `getTransaction` evidence needed for mint decimals and Pump migration verification even while Chainstack WebSocket traffic continued.

The protected Chainstack node was independently proven on the production VPS to answer standard Solana HTTPS `getTransaction` requests. Both required calls are standard read-only Solana JSON-RPC methods.

## Scope

Chainstack may now use the existing host-only `CHAINSTACK_SOLANA_WSS_URL` credential to derive its matching HTTP(S) endpoint in memory. The complete endpoint remains credential material and must never be committed, printed, logged, copied into evidence, or pasted into ChatGPT/GitHub.

The new adapter is limited to:

- `getAccountInfo` with `jsonParsed` and `confirmed` commitment for SPL mint-state evidence;
- `getTransaction` with `jsonParsed`, `confirmed`, and `maxSupportedTransactionVersion=0` for Pump creation/migration verification.

The adapter self-paces at 8 requests per second and redacts its endpoint from `Debug` output and transport failures.

## Provider roles

When Chainstack is configured:

- realtime order remains Helius -> Chainstack -> Alchemy;
- chain/mint observation includes Helius and Chainstack independently;
- Pump transaction verification selects Chainstack explicitly.

The explicit transaction selection is intentional. The current observer consumes only its first transaction adapter. A hidden Helius-to-Chainstack wrapper would make lifecycle/candidate provenance ambiguous, so this FL1 repair chooses the provider whose transport can be recorded truthfully instead of adding a larger orchestration refactor during acceptance.

When Chainstack is absent, Helius retains its existing chain and transaction roles. Alchemy remains realtime-only.

## Provenance

Chainstack mint evidence is persisted with `ProviderId::Chainstack`.

Standard transaction responses receive an internal non-secret transport marker before Pump protocol classification so verified Pump creation candidates retain `ProviderId::Chainstack` rather than the historical Helius default. Migration lifecycle events already use the selected transaction adapter's provider id.

No endpoint or credential value is placed in that marker.

## Explicit non-goals

This change does **not** grant Chainstack or any other component:

- holder-distribution authority;
- quote or execution authority;
- strategy or signal-selection authority;
- PAPER decision-policy changes;
- wallet or private-key access;
- signing or transaction-submission authority;
- LIVE authority;
- FL2 authority.

The paper-evidence daemon's existing Helius/Jupiter contract is unchanged by this repair.

## Remaining FL1.5 blockers

This RPC coverage change addresses the upstream prerequisite starvation only. Physical-host evidence also observed separate realtime fail-closed cases that remain independent until proven fixed or absent:

- PumpSwap authoritative event with zero executed quantity;
- Pump instruction/event side-count disagreement;
- a conflicting same-identity Pump economic row.

These must not be weakened as part of this RPC patch without their own production evidence and regression tests.

## Acceptance after deployment

Do not advance to FL2 or LIVE after CI/release alone.

On the physical host, prove:

1. exact sealed release and manifest are active;
2. `shreks-observe.service` remains active without restart churn;
3. raw Pump and PumpSwap evidence continue advancing;
4. new Chainstack-attributed mint/lifecycle verification evidence appears without exposing the endpoint;
5. the 8,192-row canonical frontier gains ready rows;
6. canonical FastEvents, normalization latency, and end-to-end latency samples become nonzero;
7. sequence-integrity violations remain zero;
8. no new unexplained parser/storage/restart failures occur;
9. only then run the representative 15-minute FL1.5 acceptance window.

Until those physical-host proofs pass, **FL1.5 = HOLD, FL2 = BLOCKED, LIVE = DISABLED**.
