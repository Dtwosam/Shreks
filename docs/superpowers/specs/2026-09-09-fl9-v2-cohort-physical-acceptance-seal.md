# FL9 V2 Cohort Physical Acceptance — Production Evidence Seal

**Date:** 2026-09-09  
**Sealed release SHA:** `a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2`  
**Release tag:** `shreks-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2`  
**Deployment workflow run:** `34297743260`  
**Cohort policy:** `fl9-v2-cohort-acceptance-v1`  
**Evidence-floor policy:** `fl9-v2-cohort-evidence-floor-v1`  
**Artifact fingerprint:** `bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`

## Status

The frozen FL9 V2 input-only cohort was physically generated on the production-paper VPS from the exact deployed sealed release and read back successfully with that deployed package.

This seal accepts the physical cohort identity and structural evidence floor only.

- cohort floor accepted: **YES**
- eligible identity fingerprint created: **YES**
- final V2 cohort artifact: **CREATED AND VERIFIED**
- target values inspected: **NO**
- future returns inspected: **NO**
- model training performed: **NO**
- model performance inspected: **NO**
- PnL inspected: **NO**
- PAPER promotion: **BLOCKED**
- LIVE trading: **DISABLED**

This evidence authorizes the next separately versioned V2 first-champion integration design. It does not itself authorize model training, model selection, PAPER promotion, or LIVE execution.

## Exact deployed release evidence

The protected deployment workflow succeeded for the exact immutable release:

- workflow: `Deploy verified Shreks release`
- run: `34297743260`
- head SHA: `a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2`
- release tag: `shreks-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2`
- deployment conclusion: **SUCCESS**

The VPS physically reported:

- `/opt/shreks/current` -> `/opt/shreks/releases/a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2`
- manifest source SHA -> `a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2`
- `shreks-observe.service`: active, PID 384729, restarts 0
- observer executable: exact release-local `target/release/shreks-observe`
- observer cwd: exact release directory
- `shreks-paper-evidence.service`: active, PID 384728, restarts 0
- paper-evidence executable: exact release-local `target/release/shreks-paper-evidence`
- paper-evidence cwd: exact release directory
- `shreks-paper-campaign.service`: active, PID 384747, restarts 0
- paper-campaign executable: exact release-local virtualenv Python
- paper-campaign cwd: exact release directory
- `shreks.target`: active
- cohort CLI: **PASS**
- post-deploy error journal: **NO ENTRIES**

## Physical artifact generation

The production command used the release-local entry point and read-only observer database:

```bash
sudo /opt/shreks/current/.venv/bin/shreks-fl9-v2-cohort-acceptance \
  --database /var/lib/shreks/shreks.db \
  --destination /var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2
```

Artifact path:

`/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2`

The deployed package then read the generated artifact back successfully.

## Frozen source identity

The physical artifact reconciled to the frozen V2 source contract:

- source sessions: `115,116,117,118,119,120,121,122`
- latest observed coverage session: `128`
- required latest session boundary: at least `123`
- minimum decision timestamp: `1788878323281`
- horizon: `30000 ms`
- TEST end: `1788902289835`
- selection timestamp: `1788902319835`
- training cut: `1788892302791`
- validation cut: `1788898931418`
- cross-session duplicates: `0`
- shared signatures across partitions: `0`

The later session `128` proves the frozen 115-122 source range is no longer mutable; it does not alter the accepted source population.

## Population reconciliation

Exact production counts:

| Population | Rows | Unique mints where applicable |
| --- | ---: | ---: |
| Raw source | 504,716 | 394 |
| Eligible | 274,334 | 146 |
| Training | 164,645 | — |
| Validation | 54,858 | — |
| TEST | 54,831 | — |
| Validation unseen-mint | 49,754 | 24 |
| Validation seen-mint | 5,104 | 10 |
| TEST unseen-mint | 54,828 | 31 |
| TEST seen-mint | 3 | 3 |

Eligibility reasons reconciled exactly:

- `eligible`: 274,334
- `missing_fresh_exact_market_snapshot`: 176,299
- `below_minimum_liquidity_usd`: 52,974
- `below_minimum_volume_h24_usd`: 1,109

Signature quarantine counts:

- training: 0
- validation: 0
- TEST: 0

Actor novelty counts:

- validation seen actor: 23,416
- validation unseen actor: 31,442
- validation null actor: 0
- TEST seen actor: 11,841
- TEST unseen actor: 42,990
- TEST null actor: 0

## Structural evidence-floor decision

Frozen minimums:

- eligible rows >= 250,000
- training rows >= 150,000
- validation rows >= 50,000
- TEST rows >= 50,000
- unseen-mint validation rows >= 40,000
- unseen-mint validation unique mints >= 20
- unseen-mint TEST rows >= 40,000
- unseen-mint TEST unique mints >= 25

Observed production values exceed every floor.

`structural_floor_passed=True`

The separately precommitted downstream per-target scoring floors remain:

- natural TEST scored observations >= 40,000
- unseen-mint TEST scored observations >= 35,000

Those downstream scoring floors are not evaluated by this input-only seal.

## Policy identity

The artifact authenticated the precommitted upstream identities:

- FL9 tradable-universe policy fingerprint:  
  `abfc6d21eb27d722956fbd267a10f352c887a909b3865a7a295eff95631777e4`
- FL8.3 feature-identity firewall fingerprint:  
  `e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0`

## Physical fingerprints

The generated artifact reported:

- artifact fingerprint:  
  `bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`
- accepted-decisions file SHA-256:  
  `7906567a37ec2aed5d16971803060a41f4c5cdfe9ad96781c49c8d0a7b1f088f`
- signature-quarantine file SHA-256:  
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- accepted identity fingerprint:  
  `75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b`
- training identity fingerprint:  
  `928c29224fb826ccbbf26839fb37d149a56b431910600ae2fa657fc3ca60c461`
- validation identity fingerprint:  
  `08e23802c778c7a1366a38014680ad223f0c57a8f2340b57e990f8feca43e168`
- TEST identity fingerprint:  
  `cc2720a262d3c1b07bb86d8225c4921ae6895ae76089c085e0aa332864da147e`
- validation unseen-mint identity fingerprint:  
  `ffebc5ff0e73979a139d05b3a1791c6011313dbc18dcc98e291455d5a2879f2a`
- validation seen-mint identity fingerprint:  
  `386343aeba7b1224f167c2ab40bdd6a19f6a67291ab716f0f78623f183a0c6aa`
- TEST unseen-mint identity fingerprint:  
  `f896c03590a66f4385a01a347039c9dd8a3ab60a4a181e631fa2e838e12ef285`
- TEST seen-mint identity fingerprint:  
  `9715070044400188449a4f8382fce910ea74ce65214aefed6ce49241c3ae37cd`
- signature-quarantine identity fingerprint:  
  `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`
- assessment-evidence fingerprint:  
  `0529dc6e92e2eb732e60ac6f29556fec1b539f3750e9931dbfcf94e469920e13`

The empty signature-quarantine file hashes to the canonical SHA-256 of an empty file and is consistent with zero quarantined rows.

## Decision

The FL9 V2 cohort physical-acceptance gate is satisfied.

The exact immutable source cohort has now been:

1. generated from the deployed sealed release;
2. authenticated against the frozen FL9 tradable-universe and feature-firewall policies;
3. reconciled to every precommitted source/count/split checkpoint;
4. proven signature-disjoint across chronological partitions;
5. proven above all precommitted structural evidence floors;
6. persisted to a new immutable artifact destination;
7. read back by the deployed package;
8. bound to exact file, subset, assessment, and final artifact fingerprints.

Therefore the next implementation slice may begin the separately versioned **V2 first-champion integration** that consumes this artifact exactly.

That next slice must preserve the precommitted natural-TEST and unseen-mint-TEST scoring floors and must not reinterpret or regenerate the accepted cohort silently.

## Authority boundary

This seal adds no:

- database mutation;
- cohort regeneration policy change;
- target/future-return inspection;
- model training;
- model-performance inspection;
- champion selection or promotion;
- PnL inspection;
- PAPER promotion;
- BUY authority;
- risk/sizing change;
- transaction construction;
- signing/submission;
- LIVE enablement.

**Cohort floor accepted: YES.**  
**Eligible identity fingerprint created: YES.**  
**Final V2 cohort artifact: CREATED AND VERIFIED.**  
**V2 first-champion integration: UNBLOCKED AS A SEPARATE SLICE.**  
**PAPER promotion: BLOCKED.**  
**LIVE TRADING: DISABLED.**
