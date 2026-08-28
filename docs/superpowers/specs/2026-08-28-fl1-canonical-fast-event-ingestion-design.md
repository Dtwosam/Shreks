# FL1 Canonical FastEvent Ingestion Design

## Purpose

Capture direct Pump and PumpSwap economic events into immutable raw evidence, then normalize them into a durable, replayable, strictly sequenced canonical `FastEvent` journal without guessing market identity, token decimals, or information timing.

This is the FL1 direct-event/durability/ordering implementation slice. It remains observation-only. It does not add strategy decisions, PAPER actions, execution economics, risk changes, transaction construction, signing, submission, or LIVE authority.

## Direct source topology

The production observer uses one reconnecting Helius websocket connection with confirmed Solana subscriptions for both Pump and PumpSwap programs.

The direct stream carries:

- Pump creation and migration lifecycle signals;
- Pump bonding-curve trade economics;
- PumpSwap post-graduation swap economics.

DEX Screener polling is not the authoritative Fast Lane order-flow source.

The stream parser is fail-closed:

- only successful transactions are eligible;
- program-data events are accepted only while the expected on-chain program is the active invocation;
- malformed relevant events are provider errors rather than fabricated market events;
- reconnect overlap is expected and handled by durable identity/idempotency.

## Immutable raw evidence

### Pump bonding curve

`pump_trade_evidence` preserves the direct Pump event payload keyed by `(signature, ordinal)`, including:

- provider;
- slot and first local observation time;
- mint and quote mint;
- user and side;
- raw base/quote/SOL quantities;
- event timestamp;
- raw reserve fields;
- instruction/event name.

### PumpSwap

Migration 12 adds `pump_swap_trade_evidence`. It preserves:

- provider;
- signature;
- original Solana log index;
- durable Fast Lane ordinal;
- slot and first local observation time;
- pool and user;
- side;
- executed base quantity;
- executed market quote quantity;
- separate fee-adjusted user quote quantity;
- event timestamp;
- pool reserves.

PumpSwap reserves the high half of the `u32` ordinal namespace. Its canonical ordinal is a deterministic mapping of the original log index. That keeps `(signature, ordinal)` globally usable by the shared canonical journal even when one transaction contains both bonding-curve and post-graduation evidence.

Identical raw replay is a no-op. Conflicting replay for the same immutable identity fails closed.

## Verified PumpSwap market identity

PumpSwap event payloads intentionally do not invent token mint identity. A PumpSwap raw row becomes canonical only after durable verified Pump graduation lifecycle evidence maps its pool to one unambiguous `(mint, quote_mint)` market.

For a pool:

- no verified lifecycle market -> leave the raw event pending;
- exactly one verified market -> use it;
- contradictory durable markets -> fail closed.

System SOL and wrapped SOL lifecycle quote identity are canonicalized to WSOL for the canonical market key.

## Canonical FastEvent journal

Migration 11 adds `fast_events` with:

- durable append `sequence`;
- unique economic identity `(signature, ordinal)`;
- provider, market, venue, side, actor, slot;
- chain occurrence time;
- canonical observation/acceptance time;
- original raw source-observation time;
- normalized base/quote quantities and quote price;
- exact base/quote decimals used for normalization;
- immutable source linkage appropriate to the venue.

Sequence is stable once assigned. Replay orders by `sequence`, never by a dynamic row number.

## Information-time policy

`source_observed_at_unix_ms` is when Shreks first received the immutable direct websocket evidence.

`FastEvent.observed_at_unix_ms` is when the normalized event became usable by the canonical Fast Lane path. If raw evidence arrives before required metadata is verified, it remains durable but pending. When metadata later becomes available, canonicalization uses the later normalization/acceptance clock.

This prevents late normalization from moving the Fast Lane observation clock backward while preserving the earlier source timestamp for latency measurement.

Chain occurrence time is preserved independently. A late-delivered chain event may legitimately have an older occurrence time than a previously accepted canonical event.

## Decimal provenance

The normalizer resolves decimals from durable verified evidence before constructing a canonical event:

- no verified base decimals -> pending;
- exactly one distinct verified base-decimal value -> use it;
- contradictory verified values -> fail closed;
- SOL/WSOL quote decimals -> protocol-known 9;
- non-SOL quote -> require verified quote-mint decimals;
- missing non-SOL quote decimals -> pending.

The append layer stores the exact decimal values used. It does not perform network lookup. The normalizer owns verified-decimal resolution; the storage append boundary independently recomputes normalized quantities from the immutable raw integer economics using the supplied decimal provenance and rejects any canonical payload that does not match.

## Canonical source-integrity boundary

A first canonical append cannot merely reuse a valid raw identity. Before insertion, storage rebinds the canonical payload to immutable venue-specific source truth.

For Pump bonding-curve events, storage verifies:

- provider;
- mint;
- canonical quote mint;
- side;
- actor/user;
- slot;
- occurrence timestamp;
- base quantity;
- quote quantity;
- quote price.

For PumpSwap events, storage additionally requires the verified pool-to-market lifecycle mapping and verifies the same canonical fields against the raw PumpSwap event.

PumpSwap canonical quote flow is always the executed market `quote_amount_raw`. The distinct `user_quote_amount_raw` field is retained for audit but is never substituted for canonical market order flow.

A mismatched first append fails before journal insertion or sequence consumption. Identical canonical replay is idempotent; conflicting replay fails closed.

## Bounded dual-source normalization

The observer normalizer processes at most 1,024 pending raw events per pass across both source tables in one deterministic merged order.

Ordering uses first source-observation time and stable identity tie-breakers. For each eligible row it:

1. requires the expected direct-provider provenance;
2. resolves required verified metadata;
3. obtains the next durable append sequence;
4. converts raw evidence to the provider-neutral `FastEvent` contract;
5. appends through the venue-specific source-integrity boundary;
6. leaves unresolved rows pending without fabrication.

The normalizer performs no network calls.

A bounded periodic retry lets previously pending evidence become canonical after the slower verification path writes required mint decimals or lifecycle mapping. Unexpected storage/integrity errors remain fatal to the supervised observer process rather than being silently skipped.

## Ordering, deduplication, and restart policy

Canonical sequence is append/acceptance order, not chain occurrence order.

The system explicitly supports:

- duplicate websocket delivery;
- reconnect/replay overlap;
- same-slot events;
- multiple economic events in one transaction;
- late/out-of-order chain occurrence;
- delayed metadata resolution;
- process restart.

Raw identities are immutable. Canonical `(signature, ordinal)` is unique. Sequence is derived from the durable journal and cannot reset on restart or skip ahead for a new identity.

Reopening the database preserves canonical sequence and payload exactly. Replay for one market is deterministic in sequence order.

## Realtime durability boundary

The existing realtime writer remains the single durable write boundary for the direct stream. It persists lifecycle signals and Pump/PumpSwap raw economics immediately and idempotently, then invokes bounded normalization.

The stream itself stays storage-free. Writer termination and integrity failures propagate to existing supervision instead of inventing continuity.

No additional websocket, per-trade RPC transaction fetch, strategy path, or execution authority is introduced.

## Safety boundary

This FL1 implementation is read-only with respect to capital behavior. It does not:

- create trade intents;
- change PAPER fills or ledger behavior;
- alter risk policy;
- construct Solana transactions;
- access signing authority;
- submit transactions;
- enable LIVE mode;
- start FL2 state/feature work.

Existing legacy strategy/PAPER/risk infrastructure remains available as preserved baseline infrastructure but is not granted Fast Lane authority here.

## Tested acceptance for this code slice

Repository tests prove:

- migrations preserve prior evidence and current schema reaches version 12;
- one realtime socket covers Pump and PumpSwap subscriptions;
- direct Pump and PumpSwap events decode only under the expected program context;
- raw Pump and PumpSwap evidence is immutable and idempotent;
- PumpSwap ordinal mapping is deterministic and namespace-separated;
- PumpSwap pool identity waits for verified graduation lifecycle evidence;
- missing/contradictory metadata never fabricates canonical events;
- System SOL canonicalizes to WSOL;
- PumpSwap canonical quote flow uses executed market quote, not fee-adjusted user quote;
- first canonical Pump and PumpSwap appends must match immutable raw source truth;
- canonical sequence is contiguous, restart-safe, and replay ordered;
- reconnect duplicates do not create duplicate economic events;
- normalizer work is bounded and network-free;
- runtime remains observation-only and supervised;
- Rust, Python, repository-safety, and native ARM64 CI gates pass.

## FL1.5 still required before FL2

This code slice does not claim the FL1 production exit criterion by CI alone.

Before FL2 begins, Shreks must run this stream on the real production host in read-only mode and record evidence for at least:

- raw Pump event rate;
- raw PumpSwap event rate;
- canonical event rate;
- pending/unresolved raw rows;
- chain-occurrence -> source-observation latency distribution where timestamps permit;
- source-observation -> canonical-acceptance latency distribution;
- end-to-end chain-occurrence -> canonical-acceptance latency distribution;
- duplicate/reconnect behavior;
- storage growth and resource headroom.

The FL1.5 acceptance tooling must itself be read-only, deterministic, auditable, and unable to create signing or execution authority. Real-host measurements—not CI simulation—are required before the build order may advance to FL2.
