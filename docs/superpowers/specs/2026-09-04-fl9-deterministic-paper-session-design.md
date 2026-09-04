# FL9 Deterministic PAPER Prefix-Replay Session — Design

**Date:** 2026-09-04

## Status

Design after deterministic lifecycle PAPER adapter merged as `66413bc881292cf7ce4accff975106e60cb8d0c0` (PR #174).

FL9 economic exit remains **EVIDENCE PENDING**. LIVE remains disabled.

## Problem

A full deterministic lifecycle candidate cannot safely precompute posture for an entire campaign.

Different candidates can diverge immediately:

- one entry family may BUY while another SKIPs;
- a BUY can be risk-rejected;
- a quote can be unavailable;
- REDUCE/SELL can fail or defer.

Therefore later manager decisions must be evaluated against the candidate's **actual PAPER state after prior real execution outcomes**, not against learned-policy posture and not against an assumed fill.

This matters especially for:

- lifecycle REDUCE sizing, which needs current exposure;
- FL6.5 Wallet Cohort, whose position input needs the candidate's actual opening timestamp;
- all OPEN manager rows, which must fail closed if the candidate is actually FLAT.

## Decision

Add an offline deterministic PAPER session that uses **prefix replay through the already-sealed deterministic PAPER runner**.

No new fill/risk/ledger/evaluation implementation is introduced.

For each accepted step:

1. derive expected posture from the previous prefix's actual PAPER result;
2. require the supplied deterministic lifecycle decision to match that posture/exposure;
3. append the exact decision + execution evidence;
4. build a canonical lifecycle result batch for the full prefix;
5. rerun the full prefix through `run_fast_deterministic_lifecycle_paper_candidate`;
6. store the new immutable result.

This is intentionally O(n²) and research/offline-only. Correctness and evidence integrity take priority over runtime optimization at FL9.

## Canonical lifecycle result builder

Python currently decodes canonical deterministic lifecycle result JSON but does not build a correctly fingerprinted result batch.

Add:

`build_fast_deterministic_lifecycle_results(policy, decisions)`

It:

- requires exact policy/decision types;
- runs the same lifecycle semantic validation as the decoder;
- computes the canonical `batch_fingerprint_sha256`;
- returns exact immutable `FastDeterministicLifecycleResults`.

No placeholder SHA is accepted inside the session.

## Session model

Version:

`fl9-deterministic-paper-session-v1`

Immutable session fields:

- version;
- exact deterministic candidate manifest;
- paper_run_id;
- assessment_version;
- original starting ledger;
- fill/risk/position/evaluation policies;
- accepted deterministic lifecycle decisions;
- accepted explicit PAPER evidence;
- latest full-prefix `FastCampaignPaperRunResult | None`.

The session never mutates the starting ledger. Every prefix replay begins from the same original ledger.

## Posture snapshot

Expose:

`fast_deterministic_paper_session_posture(session, market_key)`

Result:

- market key;
- posture: `FLAT` or `OPEN`;
- current exposure fraction when OPEN;
- authoritative PAPER position ID when OPEN;
- authoritative PAPER `opened_at_unix_ms` when OPEN.

### Reconstruction

Posture is reconstructed only from:

- accepted lifecycle decisions;
- authoritative BUY results;
- authoritative position-action results;
- final PAPER ledger.

Algorithm mirrors the sealed campaign executor's state transitions:

- FILLED BUY -> open market position, exposure = decision target;
- failed/aborted BUY -> remain FLAT;
- HOLD/non-terminal position result -> exposure unchanged;
- REDUCED -> exposure becomes target of the actual active exit assessment;
- SOLD -> FLAT.

All result iterators must be consumed exactly. Any contradiction fails closed.

## Step API

`apply_fast_deterministic_paper_session_step(session, decision, evidence)`

Before replay:

- exact types;
- source event IDs match;
- per-market sequence/time order preserved by canonical lifecycle builder;
- decision posture equals actual session posture;
- FLAT decision current exposure is null;
- OPEN decision current exposure equals actual session exposure within existing arithmetic tolerance.

Then full-prefix replay is executed using the exact manifest identity and sealed PAPER engine.

## Why prefix replay

This avoids:

- a second mutable PAPER state machine;
- duplicating ledger/execution logic;
- assuming fills;
- using decision intent as position truth;
- requiring Rust/Python FFI before its evidence protocol is specified.

A later Rust row-evaluation bridge can ask this session for actual posture before evaluating each next FL8.1 row.

## Tests

1. canonical Python lifecycle builder produces deterministic valid SHA;
2. initial posture is FLAT;
3. unavailable BUY leaves next posture FLAT;
4. filled BUY creates OPEN posture with exact exposure/position/open time;
5. successful REDUCE updates exposure;
6. failed/unavailable SELL keeps OPEN posture;
7. successful SELL returns FLAT;
8. wrong supplied OPEN/FLAT posture fails before replay;
9. session final result equals direct sealed runner on the same full prefix;
10. source firewall forbids provider/network/subprocess/Rust-evaluator/LIVE authority.

## Boundary

This slice does not:

- evaluate FL6 signals;
- source baseline-specific evidence;
- invoke Rust;
- fetch quotes;
- invent risk context;
- promote;
- enable LIVE.

It only makes candidate-specific PAPER posture authoritative and reusable for sequential evidence campaign orchestration.

## Next slice

Define the canonical Rust row-evaluation request/response protocol using:

- immutable FL8.1 row identity/state;
- candidate manifest;
- session-derived FLAT/OPEN state;
- explicit baseline-specific evidence.

Then connect the offline Python session to the Rust evaluator without reimplementing FL6 in Python.
