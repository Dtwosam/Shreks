# FL4 Realtime Coverage Ledger — Implementation Plan

**Date:** 2026-09-04
**Base:** `3fcae8d476dc32c63582a8dc7699abaa08bfd60e`
**Spec:** `docs/superpowers/specs/2026-09-04-fl4-realtime-coverage-ledger-design.md`

## Constraints

- Preserve existing realtime parser and `PumpRealtimeSignalSource` compatibility.
- Never infer continuity from event density or process uptime.
- Reconnect/provider switch/rebuild/process restart always breaks continuity.
- Only the current session row may extend; historical session rows are immutable.
- No strategy/PAPER/risk/promotion/signing/submission/LIVE authority.

### Task 1 — Storage contract

- [ ] Add intentional RED storage tests for absent migration/API.
- [ ] Add migration 18 `fast_realtime_coverage_sessions`.
- [ ] Add storage types and exact append/extend/read APIs.
- [ ] Require monotonic timestamp/slot/count evolution.
- [ ] Reject attempts to mutate an older session as the current session.
- [ ] Run focused storage tests and full Rust workspace.

### Task 2 — Live session identity

- [ ] Add intentional RED provider tests.
- [ ] Add connection-generation tracking to bounded Pump realtime stream.
- [ ] Add a live-only session notification wrapper.
- [ ] Add failover-level monotonic session sequencing across reconnect, provider switch, and public
      lane rebuild.
- [ ] Keep existing notification-only methods/traits behavior unchanged.
- [ ] Run provider tests and full Rust workspace.

### Task 3 — Observer persistence

- [ ] Add intentional RED observer writer tests.
- [ ] Add session-aware bounded forwarding function.
- [ ] Add session-aware realtime writer that records/extends coverage before existing evidence writes.
- [ ] Switch only the production `shreks-observe` bounded realtime path to the session-aware channel.
- [ ] Preserve existing writer API for compatibility tests/callers.
- [ ] Prove restart starts a new durable row rather than reopening the prior session.
- [ ] Run observer tests and full Rust workspace.

### Task 4 — Safety and exact-head proof

- [ ] Audit diff for provider/network expansion: none.
- [ ] Audit diff for trading/PAPER/signing/submission/LIVE authority: none.
- [ ] Run Repository safety, Rust workspace, Python suite, and native ARM64 release build.
- [ ] Require exact-head four-gate GREEN.
- [ ] Guarded merge only on the reviewed exact head.
- [ ] Require fresh merged-main four-gate GREEN and seal.

### Task 5 — Physical host evidence

- [ ] Deploy the sealed release through protected `production-paper`.
- [ ] Prove exact release SHA active.
- [ ] Prove observer/PAPER core services active.
- [ ] Let the realtime lane accumulate at least one durable coverage session.
- [ ] Read coverage rows without exposing secrets.
- [ ] Force no lifecycle change merely to manufacture proof.

### Following slice

Build the bounded FL4 event-decision population labeler. It must consume only decision horizons fully
enclosed by one stored coverage session and must select its event population chronologically without
future-outcome filtering.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
