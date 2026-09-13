# PAPER Campaign Missing Reference Price Recovery — Code Seal

## Status

**SEALED RUNTIME-RECOVERY CANDIDATE.**

This seal records implementation PR **#287**, merged on `main` at:

```text
c0920ee0fe65c0f4b1aff4ca4109986dcae04acd
```

The exact implementation PR head was:

```text
e1e0144468aca4fb65a6c7b3936a2ec479034523
```

PR CI run `34752354217` passed Repository safety, Rust tests, Python tests, and the native ARM64 release build. Python reported `3378 passed, 1 warning`. The exact merged implementation commit passed the same four canonical gates in main CI run `34752493890`.

The final `main` seal commit must retain a `seal:` subject prefix so the repository's verified-release workflow recognizes this exact source as release-authorized.

LIVE remains disabled. No FL4 production labels were changed by this implementation or its verification.

## Production condition requiring this repair

The frozen-cohort FL4 maintenance precheck halted before quiescence or database mutation because production PAPER health had drifted from the previously sealed runtime state:

- `shreks-paper-campaign.service` was failed with `NRestarts=6` after exhausting its systemd restart limit;
- `shreks-observe.service` had one restart after the authorized Solana Public realtime lane returned persistent `Unavailable`;
- the campaign restart preflight repeatedly reached `READY`, proving configuration, manifest, and durable checkpoint bootstrap remained readable;
- every actual campaign start then failed during its first real cycle.

A zero-write production replay probe isolated the campaign failure before any evidence or checkpoint persistence. Replaying the next scheduled cycle failed during aggregate candidate assembly for observer candidate `403560`:

```text
observer candidate 403560 assembly failed: observer paper cycle assembly failed: reference token price is unavailable
```

The underlying strict quote decoder rejected a route-available paper quote because the selected current observer market snapshot had `price_usd = NULL`.

A second replay at the then-current wall-clock time selected no candidates and passed assembly, pure PAPER execution, accounting validation, evidence dry-merge, and checkpoint encode-only validation. This ruled out SQLite persistence as the root cause of the campaign restart loop.

## Sealed correction

The implementation changes only quote reconstruction eligibility inside `assemble_observer_paper_cycle(...)`:

- a route-available ENTRY or EXIT quote is reconstructed only when the selected current observer market snapshot has a reference USD token price;
- if that reference price is absent, the corresponding `PaperQuote` remains `None` instead of invoking the strict quote decoder;
- the candidate itself remains in the auditable PAPER cycle and continues through the sealed feature, score, decision, and risk path;
- absence of an executable quote therefore causes the existing sealed PAPER defer/reject behavior rather than a synthetic fill or a fatal aggregate-campaign exception;
- explicit no-route evidence remains reconstructible as `PaperQuoteState.UNAVAILABLE`, including when no market reference price exists;
- malformed non-missing quote evidence still reaches the strict decoder and still fails closed.

No database schema, observer market selection policy, strategy, score policy, decision policy, risk policy, PAPER economics, checkpoint format, signer, transaction builder, submission path, or LIVE authority is changed.

## Verification proof

The repair was developed test-first against the production failure shape.

Regression-only commit:

```text
a79cd25eece8cd5512f3a3905c9b6666706dedfc
```

CI run `34752151816` failed exactly the new regression while `3377` pre-existing Python tests passed. The failure was the expected chain:

```text
ObserverPaperQuoteError: reference token price is unavailable
ObserverPaperAssemblyError: observer paper cycle assembly failed: reference token price is unavailable
ObserverCampaignCoordinatorError: observer candidate 2 assembly failed: ...
```

After the bounded assembler fix, PR CI run `34752354217` passed all four canonical lanes and Python reported:

```text
3378 passed, 1 warning
```

The PR diff contains only:

1. the aggregate-campaign missing-reference-price regression; and
2. the bounded ENTRY/EXIT quote reconstruction guard.

The exact merged implementation commit `c0920ee0fe65c0f4b1aff4ca4109986dcae04acd` then passed all four canonical lanes again in main CI run `34752493890`.

## Authorized physical continuation

After this seal lands and its immutable ARM64 release succeeds, the authorized continuation is:

1. verify the immutable `shreks-<seal-sha>` GitHub release and its release assets;
2. deploy that exact release through the protected `production-paper` deployment workflow;
3. verify `/opt/shreks/current` and `RELEASE_MANIFEST.json` resolve to the exact seal SHA;
4. verify observer, PAPER evidence, and PAPER campaign executable/cwd identities are release-local and all three core services are active/running;
5. require fresh restart counters from the new activation to remain zero and inspect fresh journals for campaign-cycle failures, SQLite contention failures, and unexpected observer failure signatures;
6. prove the PAPER campaign advances beyond its restored checkpoint instead of re-entering the missing-reference-price restart loop;
7. rerun the privileged read-only frozen-cohort/FL4 prestate because production state continued evolving while this incident was repaired;
8. only if release identity, runtime health, cohort authority, exact-cohort zero-label prestate, and scope-fingerprint gates are clean, resume the already sealed quiesce-and-backfill procedure.

Any release-identity drift, service failure/restart, recurrence of the campaign assembly failure, cohort fingerprint mismatch, source-session drift, unexpected database writer, or FL4 prestate drift is a HOLD.

## Safety boundary

This seal does **not** authorize PAPER promotion or LIVE trading. It does not authorize transaction construction, signing, or submission. It authorizes only immutable release/deployment of this PAPER runtime recovery, production PAPER health verification, and—only after those gates pass—resumption of the separately sealed historical FL4 cohort-backfill procedure.
