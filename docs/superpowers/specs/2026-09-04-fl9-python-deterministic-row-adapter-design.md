# FL9 Python Offline Deterministic Row Adapter — Design

**Date:** 2026-09-04

## Status

Design after the stateful Rust row protocol merged as `b2b1e532e60bdcfbd3c91eda7373a4763307b81a` (PR #176).

FL9 economic exit remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Create the isolated Python evidence adapter that turns:

- one exact Python FL8.1 `FastTrainingFeatureRecord`;
- one authenticated deterministic candidate manifest;
- one authoritative `FastDeterministicPaperPosture`;
- explicit baseline-specific chronological evidence;

into one exact Rust-evaluated `FastDeterministicLifecycleDecision`.

The adapter is the only Python layer in this flow permitted to launch the offline Rust row binary.

## Package boundary

Add:

`python/src/shreks_brain/fast_deterministic_offline/`

The package owns:

- row request models for explicit evidence;
- exact FL8.1 row serialization;
- exact candidate manifest serialization;
- canonical request building;
- controlled offline subprocess invocation;
- canonical response authentication and decoding.

Do **not** add subprocess imports or process-launch authority to:

- `fast_deterministic_lifecycle`;
- `fast_campaign_paper`;
- `research.fast_training_features`.

Those remain pure.

## Binary authority

Public runner:

`evaluate_fast_deterministic_row_offline(...)`

Caller must supply the exact binary path.

No hidden binary discovery, PATH fallback, cargo invocation, build step, network call, database read, or wall-clock read is allowed.

Process invocation:

- one explicit executable path;
- one temporary request JSON file;
- `subprocess.run(..., shell=False, check=False, capture_output=True, text=True)`;
- no environment mutation;
- no stdin protocol;
- nonzero exit fails closed and includes bounded stderr context;
- stdout must be non-empty canonical row-result JSON.

The temporary request file is always removed.

## Exact request serialization

### Candidate manifest

Serialize the already-decoded exact `FastDeterministicCandidateManifest` into the Rust v1 manifest shape.

The serialized object must reproduce the authenticated candidate fingerprint material exactly.

No policy threshold is accepted separately.

### FL8.1 row

Use the existing Python `FastTrainingFeatureRecord`; do not define a second record model.

The serializer must emit the exact Rust exporter JSON shape.

Important: Python's `FastTrainingReserveContext` dataclass contains fields for both reserve variants. A blind `dataclasses.asdict` would emit irrelevant null fields that the Rust exporter does not emit.

Therefore serialize reserve context by `kind`:

- `pump_curve`: only Pump curve fields;
- `pump_swap_pool`: only PumpSwap fields.

Lifecycle and window objects use their exact exporter fields.

No future labels, counterfactual outcomes, learned predictions, or PAPER results enter the row object.

### PAPER posture

Derive wire only from exact `FastDeterministicPaperPosture`:

- FLAT -> `{"kind":"FLAT"}`;
- OPEN -> current exposure + authoritative opening time.

Position ID is intentionally not sent because Rust FL6 does not consume it.

The posture market key must equal the FL8.1 row market key before launch.

## Explicit evidence models

Immutable/slotted Python dataclasses mirror the Rust row-protocol evidence only.

### Shared execution economics

- `FastOfflineExecutionLegCost`
- `FastOfflineExecutionCostModel`
- `FastOfflineExecutionTrade`
- `FastOfflineEntryExecution`

No market/timestamp fields exist.

### Entry families

- `FastOfflineImpulseScalpEvidence`
- `FastOfflineMicroPullbackEvidence`
- `FastOfflinePreGraduationEvidence`

Each carries optional execution economics.

### Graduation Flow

- `FastOfflineMarketSnapshot`
- `FastOfflineGraduationFlowEvidence`

The pre snapshot remains explicit. Current/post snapshot comes from FL8.1 in Rust.

### Wallet Cohort

- side summary;
- optional wallet evidence;
- wrapper evidence.

No candidate mint, decision time, position market, or opening time may be supplied; Rust derives them from row + PAPER posture.

### Longer Runner

- protective booleans;
- optional continuation;
- wrapper evidence.

No market/time may be supplied.

## Request validation before launch

Require:

1. exact record type;
2. exact manifest type;
3. exact PAPER posture type;
4. exact supported evidence type;
5. posture market key equals record market key;
6. evidence family equals manifest-selected entry family for FLAT or manager family for OPEN;
7. OPEN posture contains exposure/opening time;
8. all explicit numbers satisfy basic finite/sign/range constraints;
9. binary path is explicit and non-empty.

Rust remains the final semantic authority.

## Response authentication

Rust result schema:

`shreks.fast_deterministic_row_result` v1.

Python decoder must:

1. require canonical JSON bytes/text;
2. require exact fields;
3. authenticate `result_fingerprint_sha256` before semantic construction;
4. require candidate version/fingerprint exactly equal supplied manifest;
5. require returned lifecycle policy exactly equal manifest lifecycle policy;
6. construct exact `FastDeterministicLifecycleDecision`;
7. require returned source identity equals input FL8.1 row:
   - `source_event_id = decision_signature:decision_ordinal`;
   - market key;
   - sequence;
   - as-of clock;
8. require returned posture equals supplied PAPER posture.

Any contradiction fails closed.

## Testing

RED first.

Tests prove:

1. canonical request serializer matches expected Rust shape for FLAT Impulse Scalp;
2. Pump curve reserve context emits no PumpSwap-only fields;
3. PumpSwap reserve context emits no Pump-curve-only fields;
4. OPEN posture serializes session exposure/open time only;
5. wrong posture market key fails before process launch;
6. wrong evidence family fails before process launch;
7. fake offline executable returning a valid canonical result decodes to exact lifecycle decision;
8. stale/tampered result fingerprint fails;
9. wrong candidate identity fails;
10. wrong row identity fails;
11. nonzero process exit fails closed;
12. temporary request is removed;
13. pure lifecycle/PAPER packages remain free of subprocess imports;
14. adapter contains no network/database/cargo/LIVE/promotion authority.

Fixtures prove plumbing only, not edge.

## Next slice

Build the chronological deterministic campaign driver:

For each candidate and each ordered FL8.1 opportunity:

1. ask PAPER session for actual candidate posture;
2. select explicit chronological baseline evidence for that row/posture;
3. call this offline Rust row adapter;
4. append returned exact lifecycle decision + contemporaneous PAPER execution evidence to the prefix session;
5. repeat.

At campaign completion, emit the sealed `FastPolicyRunEvidence` from the session result.

Then evaluate learned-vs-required-deterministic superiority with the existing sealed FL9 proof engine.
