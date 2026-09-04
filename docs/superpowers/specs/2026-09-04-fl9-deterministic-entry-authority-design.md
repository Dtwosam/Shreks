# FL9 Deterministic PAPER Entry Authority from FL3 — Design

**Date:** 2026-09-04

## Status

Design after directional quote correction merge
`5d0edec562c7699ab9abfc742eab16d0a9401136` (#185).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Problem

The deterministic comparison path requires `FastCampaignPaperEntryAuthority` before a PAPER BUY can execute.

That authority contains:

- intended base quantity;
- exact decision executable entry price;
- FL3 maximum acceptable entry price;
- expected entry variable cost basis points;
- expected entry fixed quote cost.

Until this slice, comparison fixtures/callers could author those values independently from the FL6 execution evidence.

That is unacceptable for real proof because the maximum acceptable entry price is already canonically computed by Rust FL3 `ExecutionEconomics::assess`.

A caller must not be able to give the deterministic baseline one forecast/cost/capacity input while giving PAPER a more favorable entry boundary.

## Authoritative derivation

Add one strict offline Rust protocol:

`shreks.fast_deterministic_entry_authority_request` v1

Request fields:

- market identity;
- exact decision executable entry price;
- exact `FastEntryExecutionWire` used by FL6.

Rust requires the execution trade entry price to equal the decision entry price exactly.

It materializes the existing FL3:

- `ExecutionCostModel`;
- `ExecutionTradeInput`;
- `ExecutionEconomics::assess`.

No FL3 formula is reimplemented.

Result:

`shreks.fast_deterministic_entry_authority_result` v1

Fields:

- market identity;
- intended base quantity;
- decision executable entry price;
- FL3 maximum acceptable entry price;
- summed entry variable cost bps;
- summed entry fixed quote cost;
- SHA-256 result fingerprint.

The cost sums are only transport values required by the existing PAPER entry authority. Profitability / maximum price remains the sealed FL3 computation.

## Offline binary

Add:

`shreks-fast-entry-authority <request.json>`

The binary performs only:

`decode -> FL3 derive -> fingerprint -> encode`.

It has no provider/database/wall-clock/trading authority.

## Python adapter

Add:

`derive_fast_deterministic_entry_authority_offline(...)`.

Before launch Python requires:

- exact FL8.1 record;
- exact `FastOfflineEntryExecution`;
- execution entry price exactly equals the FL8.1 decision executable price;
- explicit existing binary path.

The result decoder authenticates:

- exact schema/fields;
- result fingerprint;
- market identity;
- decision price;
- intended quantity;
- entry variable/fixed cost assumptions against the supplied execution evidence.

It then constructs exact `FastCampaignPaperEntryAuthority`.

## Truthful no-BUY state

FL3 may derive a positive maximum acceptable entry price that is already below the decision executable price.

That is valid economics: the trade is not acceptable at the observed decision price.

The Python adapter returns `None` rather than constructing invalid PAPER BUY authority.

FL6 also treats explicit `exit_capacity_base < base_quantity` as a normal `InsufficientExitCapacity` SKIP rather than a campaign error. The adapter mirrors that sealed control-flow boundary before launching the authority binary and returns `None`. This is a direct capacity comparison, not a duplicate profitability/max-entry calculation.

This aligns with FL6: an entry baseline using the same execution evidence must SKIP when the executable entry price is above the FL3 maximum.

Accordingly candidate comparison authority can be absent. If a deterministic decision nevertheless returns BUY with no authority, the existing PAPER materializer fails closed.

## Why this precedes hydration

The real point-in-time hydrator will need to assemble:

- forecast exit price;
- exit capacity;
- cost model;
- required edge/risk margin.

Once those values are explicit, this slice provides the only approved route from that FL6 execution evidence to PAPER entry authority.

The hydrator therefore does not need to duplicate FL3 math or invent maximum entry prices.

## Authority boundary

No:

- provider/network access;
- SQLite access;
- hidden clock;
- future labels/counterfactuals;
- PAPER fill execution;
- risk decision;
- superiority evaluation;
- promotion;
- signing/submission;
- LIVE authority.

## TDD

Intentional RED head:
`1fc7fa0bebdc92f8d95da36bf367b32c50cb097b`.

Tests prove:

1. exact Rust FL3 maximum entry derivation;
2. entry variable/fixed cost transport values;
3. strict request decoding;
4. decision/execution price drift fails closed;
5. actual offline binary uses the same derivation;
6. Python authenticates result and returns exact PAPER authority;
7. below-decision FL3 maximum becomes `None`;
8. price drift fails before process launch;
9. adapter source has no network/DB/LIVE authority.

## Following slice

Build the point-in-time comparison evidence hydrator.

It must map persisted directional observer ENTRY/EXIT quote evidence plus explicit forecast/cost/capacity/regime/risk/wallet/lifecycle sources into comparison bundle v2 rows, and use this FL3 derivation for candidate entry authority.

No future labels may enter decision evidence.
