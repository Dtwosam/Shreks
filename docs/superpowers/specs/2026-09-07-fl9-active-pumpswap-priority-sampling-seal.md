# FL9 Active PumpSwap Priority Sampling — Seal

**Date:** 2026-09-07  
**Behavior merge:** `af89f58ea2501ce5d2274b4a2899e588e4002e5f`  
**Behavior main CI:** `34143705261`

## Production evidence that forced this change

The repaired migration-sampler candidate-bootstrap release
`94c784352b26a82107af2b51f0cdae89f4895ef8` was deployed successfully and remained process-stable.

Host proof established:

- exact release identity: PASS;
- `shreks-observe.service`: active;
- observer PID stable across a 75-second probe;
- observer restarts: 0;
- fatal observer journal lines: 0;
- after the first complete repaired sampler cycle, migration candidate resolution had
  `fatal_mints=0`.

The same read-only production proof exposed an independent sampler-capacity failure:

- Observer V2 registry after the first complete cycle: 784 mints;
- recent verified migrated PumpSwap mints: 524;
- first post-deploy registry flush occurred about 24.8 minutes after deployment;
- post-floor DexScreener PumpSwap snapshot mints: 597;
- fresh within 60 seconds: 22 mints;
- fresh within 60 seconds and meeting
  `liquidity >= $3,000 && volume_h24 >= $1,000`: 4 mints;
- fresh within 5 minutes: 67 mints, 34 meeting those market-quality thresholds;
- fresh within 10 minutes: 152 mints, 60 meeting those thresholds;
- snapshot-age median: 878,698 ms;
- snapshot-age p90: 1,426,601 ms;
- snapshot-age max: 1,487,861 ms.

The first-champion cohort floor remained unaccepted.

No database mutation, future-return inspection, target-value inspection, model-performance inspection,
or champion training was used to choose this fix.

## Root cause

Observer V2 previously drained every due broad candidate inside one outer sampler cycle.

Each broad candidate was sampled serially across all configured market providers.

Production free-tier pacing is:

- DexScreener market: 4 requests/second;
- Meteora market: 1 request/second.

At production registry size, unrelated broad Meteora research work therefore delayed:

- verified-migration synchronization;
- current discovery processing;
- durable registry flush;
- DexScreener observations required by the FL9 tradable-universe contract.

The 60-second FL9 snapshot-age ceiling was not being violated because the liquidity/volume thresholds
were too strict. It was being violated because the broad collector scheduler could not revisit active
decision markets promptly.

## Sealed scheduler behavior

The approved A10 broad research sampler remains active and provider-neutral.

Each outer Observer V2 cycle is now bounded.

### Active PumpSwap priority lane

Before ordinary broad work, Observer V2 selects canonical PumpSwap mints that:

1. produced a FastEvent within the last 60,000 ms; and
2. do not have a DexScreener PumpSwap snapshot at or after
   `as_of - 45,000 ms`.

Selection uses only:

- FastEvent venue/mint/timestamp;
- persisted DexScreener PumpSwap snapshot timestamps.

It consumes no:

- strategy action;
- target/future return;
- model output;
- profitability evidence;
- liquidity threshold;
- volume threshold.

Priority ordering is newest FastEvent first, then mint lexical order.

Per bounded cycle:

- maximum active priority mints: 32;
- priority provider: DexScreener only;
- operational freshness target: 45,000 ms.

The 45-second target is collection headroom beneath the unchanged FL9 eligibility ceiling of
60,000 ms. It is not a BUY threshold and it does not change tradable-universe policy semantics.

Priority snapshots use the ordinary normalized `market_snapshots` write path and may finalize
already-due A9 checkpoints.

Priority observations do not rewrite the A10 representative-path scheduling state. A mint sampled by
the priority lane is skipped from ordinary broad work in the same outer cycle to avoid an immediate
duplicate provider call.

### Bounded broad A10 work

After priority work, at most one ordinary due candidate is sampled through all configured broad
market providers in that outer cycle.

The ordinary queue still preserves:

- deterministic due ordering;
- adaptive A10 age/activity scheduling;
- DexScreener research snapshots;
- Meteora research snapshots;
- candidate neutrality;
- 24h + 10m research retention;
- provider health/error behavior;
- A9 checkpoint finalization.

This converts one many-minute monolithic cycle into continuously bounded cycles so migration sync
and registry persistence remain live under backlog.

## Storage selector

A new point-in-time storage selector identifies recently active PumpSwap mints whose DexScreener
PumpSwap market evidence is older than the operational 45-second target.

The selector:

- reads only the supplied recent FastEvent interval;
- never reads future timestamps;
- filters venue exactly `pump_swap`;
- compares only persisted market snapshot timestamps;
- returns a deterministic bounded result.

Tests preserve canonical FastEvent source-evidence integrity rather than bypassing storage triggers.

## Regression evidence

Behavior PR #242 proved:

- recent PumpSwap activity without a sufficiently fresh DexScreener snapshot is selected;
- bonding-curve and stale-activity rows are not selected;
- a snapshot exactly at the freshness floor is treated as fresh;
- active PumpSwap priority sampling calls DexScreener without waiting for Meteora broad work;
- a priority mint is not immediately re-sampled through broad work in the same cycle;
- ordinary broad sampling is bounded to one due candidate per outer cycle;
- existing discovery, adaptive path, multi-provider persistence, migration bootstrap, restart,
  checkpoint, provider-failure and safety tests continue to pass.

The first test fixture attempt correctly failed because the production schema rejected a synthetic
PumpSwap FastEvent without immutable PumpSwap source evidence. The fixture was corrected to preserve
the canonical source-integrity contract.

Merged-main CI run `34143705261` on
`af89f58ea2501ce5d2274b4a2899e588e4002e5f` completed:

- Repository safety: PASS
- Rust tests: PASS
- Python tests: PASS
- ARM64 release build: PASS

## Tradable-universe contract remains unchanged

This seal does not revise `fl9-tradable-universe-v1`.

First-champion BUY eligibility still requires:

- venue exactly `pump_swap`;
- verified Pump.fun bonding-curve -> PumpSwap migration known by decision time;
- canonical DexScreener PumpSwap snapshot at or before the decision;
- snapshot age <= 60,000 ms;
- liquidity >= $3,000;
- trailing 24h volume >= $1,000;
- missing/stale/ambiguous evidence = SKIP.

Bonding-curve decisions remain never BUY-eligible.

The $3,000/$1,000 thresholds are unchanged.

## Post-deploy evidence gate

No champion cohort floor is accepted yet.

After deployment of this sealed scheduler release, production must prove:

- exact release identity;
- observer PID/restart stability;
- registry checkpoint advances continuously;
- no migration candidate-resolution fatal;
- active PumpSwap decision markets receive fresh DexScreener snapshots;
- decision-time <=60s snapshot coverage materially improves;
- the final market-quality-eligible cohort has adequate mint diversity and acceptable
  concentration.

If active-decision 60-second coverage still cannot be sustained, any change to snapshot-age policy
requires a separately versioned input-only operational evidence decision. Outcome/model evidence
must not influence that decision.

## Authority boundary

This seal adds no:

- FL4 label mutation;
- future-label/outcome input;
- model training;
- model promotion;
- BUY decision authority;
- transaction construction;
- signing/submission;
- wallet authority;
- LIVE enablement.

**FL9 superiority: EVIDENCE PENDING.**  
**LIVE TRADING: DISABLED.**
