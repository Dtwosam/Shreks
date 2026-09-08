# FL8.3 Validation V2 — Chronological Generalization Without Impossible Entity Quarantine

**Date:** 2026-09-08  
**Base:** `8d424913df27066ab2c0f67e8093b71ec3c3bcac`  
**Status:** DESIGN — approved in chat, pending written-spec review  
**Supersedes for FL9 first-champion work:** the entity-quarantine semantics of `fl8.3` V1 only; all unrelated FL8.3 contracts remain preserved  
**LIVE:** DISABLED

## 1. Purpose

Replace the production-infeasible FL8.3 V1 rule that quarantines every row carrying a mint or decision actor shared across train/validation/TEST with a validation contract that still proves genuine chronological generalization.

The replacement must:

- remain deterministic;
- preserve strict chronology;
- preserve strict future-label maturity;
- preserve strict transaction/event isolation;
- prevent raw entity identifiers from becoming model features;
- evaluate future market behavior on the natural eligible distribution;
- separately measure transfer to genuinely unseen mints;
- retain auditable fingerprints;
- keep target/model/PnL evidence outside split construction;
- keep LIVE disabled.

The objective is not to make validation easier. It is to make validation answer the production-relevant question without destroying the evaluation population.

## 2. Production evidence requiring the change

The immutable FL9 v1 population over coverage sessions 115, 116, and 117 contains:

- 138,864 PumpSwap decisions;
- 120 observed PumpSwap mints;
- 80,330 v1-eligible decisions;
- 41 eligible mints;
- no missing verified migration;
- no contradictory verified migration;
- no candidate identity failures.

The input-only 60/20/20 preflight produced:

- training raw: 48,165 rows / 38 mints;
- validation raw: 16,191 rows / 7 mints;
- TEST raw: 15,974 rows / 10 mints.

Under sealed FL8.3 V1 entity quarantine:

- shared mints: 9;
- shared actors: 6,610;
- shared signatures: 0;
- training: 48,165 -> 24,758 rows;
- validation: 16,191 -> 0 rows;
- TEST: 15,974 -> 428 rows / 2 mints.

A mint-actor connected-component audit over the same immutable eligible population showed:

- eligible unique actors: 21,079;
- actors trading multiple eligible mints: 1,294;
- connected components: 2;
- largest component: 80,329 / 80,330 rows = 99.9988%;
- that component spans training, validation, and TEST;
- the only other component contains one training row.

Therefore exact mint+actor disjointness across chronological partitions is structurally infeasible for this real PumpSwap population.

This is not a small-data problem. More observations from the same market are likely to increase entity connectivity rather than create isolated chronological components.

## 3. Source-of-truth alignment

`SHREKS_MASTER_SOURCE_OF_TRUTH.md` requires:

- point-in-time-safe features;
- chronological evaluation;
- no look-ahead leakage;
- wallet/cohort behavior as learnable market information;
- repeatable unseen evidence before promotion;
- positive net expectancy after realistic costs;
- no silent self-promotion;
- LIVE disabled until proof.

`SHREKS_BUILD_ORDER.md` requires FL8.3 validation to be:

- time-aware;
- resistant to wallet/token/event leakage.

Neither higher-level source requires every repeated mint or wallet identity to be absent from later chronological partitions.

V2 therefore interprets “resistant to entity leakage” as:

1. raw entity identifiers cannot become memorization features;
2. future data cannot influence training features or split construction;
3. exact transaction evidence cannot straddle partitions;
4. natural future chronology remains untouched for primary evaluation;
5. novelty-specific evaluation explicitly measures generalization to entities unseen during training.

This preserves the architectural intent while removing an empirically impossible implementation constraint.

## 4. Non-goals

V2 does not:

- weaken `fl9-tradable-universe-v1`;
- change the $3,000 liquidity threshold;
- change the $1,000 h24 volume threshold;
- change the 60-second market-snapshot freshness rule;
- change FL4 labels;
- inspect target values while selecting rows or boundaries;
- inspect returns/PnL while selecting rows or boundaries;
- add mint balancing;
- add actor balancing;
- add random sampling;
- add random train/test splits;
- tune boundaries against model performance;
- permit transaction/signature leakage;
- permit future labels into features;
- authorize a champion;
- authorize PAPER promotion;
- authorize LIVE.

## 5. Selected architecture

Introduce a new validation policy/version rather than mutating V1 semantics in place.

Conceptual version:

`fl8.3-chronological-generalization-v2`

The existing V1 implementation remains available for backward compatibility and sealed historical evidence.

V2 is a sibling validation path that preserves the existing data models where practical but has explicit new policy/fingerprint semantics.

### 5.1 Primary evaluation population

The primary validation and TEST populations are the exact natural chronological eligible rows inside the frozen intervals.

Rows are not removed merely because:

- the mint appeared earlier;
- the actor appeared earlier;
- the mint appears in another partition;
- the actor appears in another partition.

This primary population answers:

> Does the training-only model generalize to the actual future PumpSwap distribution Shreks will encounter?

### 5.2 Novelty evaluation slices

For every future partition, V2 derives deterministic input-only novelty classifications relative to the **training partition only**.

Required slices:

- `all_future`
- `unseen_mint`
- `seen_mint`

Required actor diagnostics:

- `unseen_actor`
- `seen_actor`

Optional cross-product counts may be reported, but V2 must not require enough rows in every cross-product slice to train or run.

Definitions:

- unseen mint: row mint does not occur in raw training;
- seen mint: row mint occurs in raw training;
- unseen actor: non-null row actor does not occur in raw training;
- seen actor: non-null row actor occurs in raw training;
- null actor remains an explicit null-actor category and is not silently classified as unseen.

The model is always the same training-only artifact. Novelty slices change reporting/evaluation population only, never the fit.

The required generalization question is:

> Does performance remain acceptable on future rows from mints the model never observed during training?

### 5.3 Why unseen mint is mandatory

Current model features do not include the raw mint identifier.

However, repeated mint regimes can still create correlated market-state patterns and can make natural chronological TEST easier than transfer to brand-new launches.

An unseen-mint slice therefore provides a direct stress test against mint-specific memorization through correlated features.

A first champion may not claim generalization solely from the natural TEST population if the unseen-mint TEST slice is empty or below its explicit precommitted evidence floor.

### 5.4 Why actor novelty is diagnostic rather than a row-deletion rule

Current FL8.2 feature extraction does not expose raw actor identity. It exposes:

- whether a decision actor exists;
- aggregate rolling unique buyer/seller counts;
- aggregate flow/microstructure values.

It does not expose:

- wallet address;
- wallet hash;
- wallet embedding;
- actor-specific historical identity key.

Therefore repeated wallet identity is not directly learnable by the current model family.

Actor novelty still matters as a robustness diagnostic because recurring wallets can create correlated flow patterns, but deleting every row touched by a recurring wallet destroys almost the entire real market.

If a future feature schema adds actor-specific identity/history features, this design must be revisited before that schema is admitted to V2.

## 6. Identity-blind feature firewall

V2 requires an explicit versioned feature-identity firewall.

For the currently sealed forecast feature schema, the following raw identifiers are forbidden from model inputs:

- mint;
- quote mint identity;
- pair/pool address;
- decision actor address;
- transaction signature;
- ordinal;
- sequence as an identity proxy;
- provider identity;
- lifecycle transaction signature;
- arbitrary hashes/encodings/embeddings derived from any forbidden raw identity.

Permitted features include point-in-time market state and aggregate descriptors such as:

- executable price;
- reserve values;
- lifecycle age;
- buy/sell counts;
- aggregate unique actor counts;
- flow imbalance;
- flow velocity/acceleration;
- local high/low;
- drawdown/recovery;
- actor-present boolean.

A versioned firewall fingerprint must cover the exact allowed model feature names and forbidden identity classes.

If the feature schema changes, V2 must fail closed until the new schema is explicitly reviewed against this firewall.

## 7. Chronological split contract

V2 preserves the existing first-champion deterministic 60/20/20 boundary construction:

1. determine the selection timestamp externally;
2. compute `test_end = selection_at_unix_ms - horizon_ms`;
3. retain only rows earlier than `test_end`;
4. group equal decision timestamps so equal timestamps cannot straddle partitions;
5. choose the closest-to-60% training boundary by raw eligible row count;
6. choose the closest-to-80% validation/TEST boundary;
7. use half-open intervals;
8. never move a boundary after target/model inspection.

The primary fold remains:

- training: `[start, training_cut)`
- validation: `[training_cut, validation_cut)`
- TEST: `[validation_cut, test_end)`

No randomness is permitted.

## 8. Transaction/event isolation

Exact event isolation remains mandatory.

No decision signature may appear in more than one partition.

If signature reuse crosses a partition boundary:

- every row carrying that signature is quarantined from all affected partitions;
- the quarantine is deterministic;
- the quarantined identity set is fingerprinted;
- an empty post-signature-quarantine partition fails closed.

V2 does not relax event/transaction leakage because a transaction is the same underlying economic evidence, unlike a mint or wallet that can legitimately recur at later independent decision times.

## 9. Future-label and maturity firewall

All V1 future-label protections remain.

Training rows used for fitting must satisfy:

- exact requested horizon exists;
- label completeness is complete;
- selected target is non-null and type-valid;
- `decision_observed_at_unix_ms + horizon_ms <= validation_started_at_unix_ms`.

Validation and TEST target values remain unread until after predictions are generated.

No validation/TEST target value may influence:

- split boundaries;
- eligible population;
- training population;
- novelty classification;
- feature transforms;
- model coefficients;
- model selection;
- prediction identities.

## 10. Natural-distribution and novelty evidence

Every V2 run must preserve prediction identities for:

### Validation

- all validation rows;
- unseen-mint validation rows;
- seen-mint validation rows;
- unseen/seen/null actor counts.

### TEST

- all TEST rows;
- unseen-mint TEST rows;
- seen-mint TEST rows;
- unseen/seen/null actor counts.

The underlying prediction for a row must be identical regardless of which slice later references it.

Slices are views over one frozen future prediction population, not independently fitted models.

## 11. Precommitted evidence floors

V2 must not invent thresholds after seeing model performance.

Before any target/model-quality inspection, the first-champion request must explicitly carry minimum evidence floors for at least:

- raw training rows;
- raw validation rows;
- raw TEST rows;
- unseen-mint validation rows;
- unseen-mint TEST rows;
- unique unseen-mint count in validation;
- unique unseen-mint count in TEST.

The exact numeric production floors are a separate evidence-policy choice and must be frozen before the first V2 target/model evaluation.

They must not be selected by maximizing accuracy, return, PnL, or acceptance probability.

If the immutable population cannot satisfy the frozen floors, collection continues or the policy is explicitly redesigned. The planner does not search alternate boundaries after seeing the failure.

## 12. Mint concentration

V2 does not add balancing by default.

Reason:

The immutable 115–117 raw training partition already showed materially healthier distribution than the full eligible population:

- 48,165 raw training rows;
- 38 mints;
- top-1 share: 13.0883%;
- top-3 share: 34.5562%;
- top-5 share: 53.2046%;
- effective mint count: 13.0684.

The V1 entity quarantine worsened training concentration:

- 24,758 rows;
- 29 mints;
- top-1 share: 20.8135%;
- top-3 share: 59.5767%;
- effective mint count: 7.3688.

Therefore no mint-balance policy is justified yet.

After V2 creates a valid natural chronological evaluation path, training balance may be reconsidered only if input-only evidence shows the actual V2 training population remains materially dominated across sustained immutable cohorts.

Any balancing policy must be separately versioned and precommitted before target/model inspection.

## 13. Determinism and fingerprints

A V2 validation run fingerprint must cover at least:

- validation schema/version;
- training bundle fingerprint;
- eligible population fingerprint;
- tradable-universe policy fingerprint;
- feature-identity-firewall version/fingerprint;
- split-policy version;
- exact fold boundaries;
- exact signature quarantine identities/fingerprint;
- training decision identities;
- validation prediction identities;
- TEST prediction identities;
- unseen-mint validation identities;
- unseen-mint TEST identities;
- seen-mint validation identities;
- seen-mint TEST identities;
- novelty counts;
- model artifact fingerprint.

Equivalent inputs must produce the same result independent of source ordering.

## 14. Public result semantics

V2 result models must make the distinction between primary population and novelty slices explicit.

At minimum, the fold result needs:

- raw training/validation/TEST counts;
- post-signature-quarantine counts;
- signature quarantine summary;
- training unique mint count;
- validation unique mint count;
- TEST unique mint count;
- unseen-mint validation row and mint counts;
- unseen-mint TEST row and mint counts;
- seen-mint validation row count;
- seen-mint TEST row count;
- seen/unseen/null actor diagnostic counts;
- model artifact;
- natural validation predictions;
- natural TEST predictions;
- novelty identity sets or deterministic fingerprints sufficient to reconstruct the slices.

Raw wallet addresses should not be copied into public report objects unless an existing audited evidence surface already requires them. Counts and fingerprints are preferred.

## 15. Compatibility

### 15.1 V1 remains immutable

Existing:

- `FastChronologicalValidationPolicy`
- `run_fast_chronological_validation(...)`
- V1 fingerprints
- V1 tests

remain behaviorally unchanged.

V2 must not silently reinterpret old V1 policies or artifacts.

### 15.2 First-champion integration

The FL9 first-champion planner/builder must opt into V2 explicitly through a versioned request/policy.

A V1 first-champion request must continue to execute V1 semantics and fail as before.

A V2 first-champion request must fail closed if:

- V2 policy version is unknown;
- feature firewall fingerprint is wrong;
- novelty evidence floors are missing;
- unseen-mint required slice is below floor;
- signature isolation fails;
- target maturity fails;
- source/fingerprint reconciliation fails.

## 16. Error handling

V2 fails closed for:

- malformed chronology;
- overlapping evaluation intervals;
- duplicate decision identities;
- equal timestamp rows split across partitions;
- signature overlap surviving quarantine;
- empty primary train/validation/TEST;
- insufficient frozen novelty floors;
- raw forbidden identity entering the model feature schema;
- feature firewall fingerprint mismatch;
- future label read before prediction;
- target maturity failure;
- source fingerprint contradiction;
- non-deterministic novelty identity reconstruction;
- model training/inference failure.

It must not respond to these failures by:

- trying a different chronological cut;
- deleting a dominant mint;
- deleting recurring actors;
- reducing evidence floors;
- weakening tradable-universe thresholds;
- inspecting PnL and choosing the split that looks best.

## 17. TDD requirements

Implementation requires independent RED -> GREEN proof for at least:

1. V1 behavior remains byte/fingerprint compatible;
2. V2 preserves exact 60/20/20 chronology;
3. same transaction signature crossing partitions is quarantined;
4. repeated mint across partitions is retained in V2;
5. repeated actor across partitions is retained in V2;
6. raw mint/actor/signature identities cannot enter the forecast feature vector;
7. unseen-mint classification is relative only to training;
8. a mint first appearing in validation and recurring in TEST remains unseen relative to training in both;
9. seen-mint classification is deterministic;
10. null actors are distinct from unseen actors;
11. actor novelty does not alter fit/predictions;
12. novelty slices reference the same prediction values as the natural future population;
13. validation/TEST labels cannot influence split or novelty membership;
14. training horizon maturity remains enforced;
15. unseen-mint row/mint floors fail closed before model-quality evaluation;
16. exact novelty identities/fingerprints are deterministic;
17. malformed feature-firewall version/fingerprint fails closed;
18. current sealed FL8.2 feature schema passes the identity firewall;
19. a fixture feature schema containing raw mint or actor identity fails the firewall;
20. first-champion V1 requests retain V1 semantics;
21. first-champion V2 requests require explicit V2 evidence fields;
22. all four sealed FL8.2 baseline families run through V2;
23. no network/database/write/PAPER/LIVE authority enters the pure validation engine;
24. production-shaped giant mint-actor connected fixtures still produce non-empty V2 validation and TEST populations.

## 18. Production acceptance sequence

Before first genuine V2 champion training:

1. implement and seal V2 under TDD;
2. merged-main CI must pass;
3. if runtime code used on the VPS changes, deploy exact sealed release and verify physical identity;
4. rerun an input-only V2 preflight over the accepted immutable FL9 population;
5. freeze the exact eligible identities;
6. freeze the exact V2 split;
7. freeze novelty evidence floors and verify they are met;
8. create eligible/split/novelty fingerprints;
9. only then allow target values to be read for training/evaluation;
10. train the first challenger;
11. evaluate natural chronological TEST;
12. evaluate unseen-mint TEST separately;
13. apply realistic cost/capacity economics;
14. proceed to PAPER/shadow only if evidence supports it;
15. LIVE remains disabled until the existing promotion gates are satisfied.

## 19. Profitability interpretation

V2 is designed to avoid two false conclusions.

### False positive avoided

A model that looks strong only because it repeatedly sees correlated behavior from the same few tokens should be exposed by the unseen-mint TEST slice.

### False negative avoided

A model should not be declared impossible merely because active PumpSwap wallets and mints naturally recur across time. Recurrence is part of the production market distribution and must remain in the primary chronological evaluation unless the raw identity itself enters the model.

The first champion must therefore prove both:

1. performance on the natural future distribution;
2. transfer to genuinely unseen mints.

Neither alone is sufficient evidence of a durable trading edge.

## 20. Authority boundary

This design authorizes no implementation by itself.

It changes no:

- database;
- runtime sampler;
- tradable-universe policy;
- label values;
- training outputs;
- champion;
- PAPER action;
- risk policy;
- transaction path;
- LIVE setting.

Until implementation is separately reviewed, planned, tested, merged, and physically verified where required:

- cohort floor accepted: **NO**
- eligible identity fingerprint created: **NO**
- final 60/20/20 split: **BLOCKED**
- champion training: **BLOCKED**
- FL9 superiority: **EVIDENCE PENDING**
- LIVE trading: **DISABLED**
