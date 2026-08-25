# Phase E15 Observer Paper Campaign Verification Record

**Phase:** E15 — Observer Paper Campaign  
**Verification date:** 2026-08-25  
**Stacked PR:** #39  
**Sealed E14 base:** `72e18c82a8477936479fd13b4f00f52a71c0f59d`  
**Frozen E15 behavior head:** `7deb85a4215f72a97bc473991c53be73050d4bca`

## 1. Verified purpose and boundary

E15 converts real point-in-time observer history into purpose-correct, restart-safe paper cycles and E11 evaluation evidence. It adds bidirectional ENTRY/EXIT quote evidence, read-only campaign reconstruction, purpose-correct paper quote conversion, dynamic paper risk context, Fresh Launch cycle assembly, restart-safe campaign execution, and a restricted public API.

E15 does **not** prove profitability and does **not** authorize live money. It does not add registry mutation, promotion, E12 auto-promotion, live execution, transaction construction, signing, submission, or credential authority. Real positive expectancy remains an empirical claim that must be demonstrated by an independent real paper campaign after this seal.

The following sealed behavior was not modified in E15: B1 safety thresholds/precedence, B2 feature arithmetic, B6 regime classification, C5 orchestration, C6 accounting/checkpoint behavior, E11 normalization, E12 proof gates, E6 registry mutation behavior, E8 promotion behavior, and live execution behavior.

## 2. Immutable verification anchors

Each implementation unit followed RED -> inspect intended failure -> minimal GREEN -> full repository CI. The final GREEN checkpoint for each task is listed with the exact CI run used as the task-level repository verification.

| Task | RED anchor(s) | GREEN anchor(s) | Final GREEN CI |
| --- | --- | --- | --- |
| 1 — purpose-attributed quote persistence | `51733ea7288f816234d0a956195cf40455aab442` quote-purpose contract; `a150aec8b4f119c0a7e931b28a4aeecb7a15946b` migration contract; `299ed01be0b2f861f868528fb324049fb84b15e0` generic storage contract | `39028536bfaa2017cbef0af04f9b589a1d95e919` quote vocabulary; `379a57ed1cc1fcd0fddecc538130decf8de39fb6` migration; `b60d8acdd2c44869b1a7b78cfd7d6b507e2a358a` migration registration; schema-preservation follow-ups `4d9d0c0563ec0bbe54a1d7e20be765e3128d1049`, `4255d7b48f0e4ab486c09cfabd7243d8ec77d5de`, `dd8f17f2bbbe11c03d5edbb403ec8d44b0d65cb6`, `64b710d5a71dfd03b34660f8098d995f6a9def34`; `b8819460a1266d9ada93aae15cb0eee9480aafaa` generic persistence | `32870808387`: Python **2182 passed in 8.57s**; Rust GREEN; repository safety GREEN |
| 2 — bidirectional explicit collector | `bc3371603a988ba15edf1e690472659f0985e917` collector contract; `b0d4e7376024303982b2c1b1379c7b63cab78d94` purpose-counter contract | `0d42c61596098cb2bc29e2c004e208fab20076d6` bidirectional collection; `d359ed63c7a5c0cd3cc5a0e5016a512fbd7b3be0` E14 regression adaptation; `10fd056bbf97d570cfb286097c98cf3db8b6b359` purpose counters | `32871700517`: Python **2182 passed in 10.18s**; Rust GREEN; repository safety GREEN |
| 3 — evidence models/read-only store/regime replay | `0e25f3b9cfd47c2b6c6d9eb31d38f491f4e3f50c` models; `20f4e095b4b222067453b078a7b44e58e6342a1f` store; `9181ba15a8f3398576579d3d4527c47d7385152a` aggregate regime | `87bc8d375e0dde2144deb1afe8dc3c458205ca79` models; `74aef5b4e60b9de2bdac71f4f18c46c53bd1f237` store; `025d26c494b0cb6da5b2c8ea42ab26962c04d8c6` aggregate regime | `32874880435`: Python **2195 passed in 7.98s**; Rust GREEN; repository safety GREEN |
| 4 — purpose-correct quote reconstruction | `de6e324296e508c9dd76816e8de0803d68034a69` | `da879c0959e4126cbdd031fac5cc5ff298d7e6a1` | `32875400987`: Python **2202 passed in 8.17s**; Rust GREEN; repository safety GREEN |
| 5 — dynamic paper risk context | `362376910f98ae30bafc7b76f0b4c4cc3eb6e100` | `eed92c8c3694c89a87beaa0b4dcffc08c0dae70d` | `32876007003`: Python **2207 passed in 8.82s**; Rust GREEN; repository safety GREEN |
| 6 — Fresh Launch observer cycle assembler | `a3ddcee9bb7877becaf397dbb0b5345f3e2cb8d9` | `16f8b6c19c0e32755111c519a1aeb60f76719de4`; value-comparison test correction `c322c4635de88f297ab05058b84792f613fb0b95` | `32878019339`: Python **2214 passed in 8.10s**; Rust GREEN; repository safety GREEN |
| 7 — restart-safe runner/E11 bridge | `4aec843fdad23047517774f1c48619d0bc534ea2` | `6fc8d2ac60af5dbe50427e27c94ac41e1ef40e6b`; latency-boundary test correction `45e454cd7aa21a23d4f7ff52f21752b2fa8b07d3` | `32879194087`: Python **2220 passed in 8.63s**; Rust/workspace GREEN; repository safety GREEN |
| 8 — public API/authority firewall | `4f9b41083bb4a4b39525b637d6f76c7cdf1ec214` | `7deb85a4215f72a97bc473991c53be73050d4bca` | `32885314743`: Python **2225 passed in 8.50s**; Rust GREEN; repository safety GREEN |

### Task 8 RED proof

The Task 8 RED CI was run `32885137174`. Python produced **4 failed, 2221 passed in 8.82s**. All four failures were the intended missing-public-package-surface failures before `observer_campaign/__init__.py` existed. No unrelated regression was present. The export-only implementation then produced the frozen behavior head above.

## 3. Exact E15 public API

`shreks_brain.observer_campaign.__all__` is exactly:

```text
OBSERVER_PAPER_CAMPAIGN_SCHEMA_VERSION
ObserverPaperQuotePurpose
ObserverPaperQuoteAsset
ObserverPaperQuoteIdentity
ObserverPaperQuoteEvidence
ObserverRegimeReadPolicy
ObserverPaperRiskEnvironment
ObserverCampaignReadError
ObserverCampaignStore
ObserverPaperQuoteError
build_entry_paper_quote
build_exit_paper_quote
ObserverPaperRiskContextError
build_observer_risk_context
OBSERVER_PAPER_CYCLE_AUDIT_SCHEMA_VERSION
ObserverPaperAssemblyError
ObserverFreshLaunchPolicyBundle
ObserverPaperCycleAudit
assemble_observer_paper_cycle
ObserverPaperCampaignError
ObserverPaperCampaignRunner
```

The public `ObserverCampaignStore` callable surface is restricted to:

```text
latest_paper_quote
latest_token_decimals
build_regime_market_window
```

The public `ObserverPaperCampaignRunner` callable surface is restricted to:

```text
load_state
run_cycle
evaluated_trades
```

The authority-firewall tests reject promotion/live/execution imports, authority-bearing public names, and fresh-process loading of promotion/live/execution modules. The only registry dependency allowed by the E15 package is the sealed read-only attribution type `RegistryCandidate`.

## 4. Sealed E14 -> frozen E15 behavior scope audit

The immutable comparison `72e18c82a8477936479fd13b4f00f52a71c0f59d` -> `7deb85a4215f72a97bc473991c53be73050d4bca` contains **32 changed files**. Every file was inspected and classified below.

### Project architecture documentation — approved, documentation only

| File | Audit result |
| --- | --- |
| `SHREKS_MASTER_SOURCE_OF_TRUTH.md` | User-approved production runtime/monitoring architecture only: GitHub control plane, dedicated Linux VPS runtime, dashboard/alerts, emergency controls, recovery, runtime secret boundary. No trading behavior. |
| `SHREKS_BUILD_ORDER.md` | User-approved Phase G operations sequencing aligned to the master source. No trading behavior. |

### E15 design/verification documentation

| File | Audit result |
| --- | --- |
| `docs/superpowers/specs/2026-08-25-phase-e15-observer-paper-campaign-design.md` | E15 design contract and authority boundary. |
| `docs/superpowers/plans/2026-08-25-phase-e15-observer-paper-campaign.md` | Implementation plan at behavior head; this file becomes this verification record in the seal commit. |

### Rust core/storage — additive quote-purpose evidence only

| File | Audit result |
| --- | --- |
| `crates/shreks-core/src/lib.rs` | Adds provider-neutral `QuotePurpose` vocabulary; no strategy/risk/live authority. |
| `crates/shreks-core/tests/quote_purpose.rs` | Exact purpose-vocabulary contract. |
| `crates/shreks-storage/migrations/0009_paper_quote_purpose.sql` | Additive purpose-attributed paper quote persistence. No transaction/signature fields. |
| `crates/shreks-storage/src/lib.rs` | Registers schema 9 and generic paper-quote insertion while retaining E14 exit storage. |
| `crates/shreks-storage/src/safety_evidence.rs` | Append-only purpose-attributed persistence with replay idempotence and contradiction rejection. |
| `crates/shreks-storage/tests/database.rs` | Schema 9 expectation only. |
| `crates/shreks-storage/tests/outcome_checkpoints.rs` | Schema 9 expectation only. |
| `crates/shreks-storage/tests/pump_migration_storage.rs` | Schema 9 expectation only. |
| `crates/shreks-storage/tests/safety_evidence_storage.rs` | Schema 9 expectation only. |
| `crates/shreks-storage/tests/paper_quote_storage.rs` | ENTRY/EXIT identity, u64 text persistence, route-label canonicalization, replay/idempotence/contradiction tests. |

### Rust explicit collector — opt-in bidirectional evidence only

| File | Audit result |
| --- | --- |
| `crates/shreks-observer/src/safety_evidence.rs` | Explicit safety collector extended to separately obtain/persist purpose-correct EXIT and optional ENTRY evidence. Provider failures remain nonfatal/unknown. |
| `crates/shreks-observer/tests/paper_quote_collection.rs` | Bidirectional purpose attribution, no-route, failure isolation, identity rejection, idempotence, and default-observer non-opt-in coverage. |
| `crates/shreks-observer/tests/safety_evidence.rs` | E14 safety collector regression coverage adapted to the explicit E15 probe shape; sealed B1 safety behavior unchanged. |

The default Phase-A observer path remains unchanged and does not silently construct the E15 safety/campaign collector.

### Python isolated `observer_campaign` package

| File | Audit result |
| --- | --- |
| `python/src/shreks_brain/observer_campaign/models.py` | Immutable/versioned evidence, quote identity, regime-read policy, and explicit health/risk environment contracts. |
| `python/src/shreks_brain/observer_campaign/store.py` | Read-only SQLite access; exact point-in-time/purpose/request attribution; no DB creation or mutation. |
| `python/src/shreks_brain/observer_campaign/quotes.py` | Purpose-correct ENTRY/EXIT paper quote arithmetic; unavailable route stays unavailable; no synthetic fill. |
| `python/src/shreks_brain/observer_campaign/risk_context.py` | Derives risk context from actual paper state/evidence; no optimistic health defaults. |
| `python/src/shreks_brain/observer_campaign/assembler.py` | Composes sealed B1/B2/B6/C5-facing inputs for Fresh Launch only; unsupported setups fail closed; no duplicated thresholds. |
| `python/src/shreks_brain/observer_campaign/runner.py` | Restart-safe C5/C6/E11 bridge; checkpoint/evidence contradictions fail closed; no E12 promotion or live path. |
| `python/src/shreks_brain/observer_campaign/__init__.py` | Export-only authority-limited public surface. |

### Python E15 tests

| File | Audit result |
| --- | --- |
| `python/tests/test_observer_campaign_models.py` | Exact immutable schema and authority-free contracts. |
| `python/tests/test_observer_campaign_store.py` | Read-only/PIT/purpose attribution and future-row invisibility. |
| `python/tests/test_observer_campaign_regime_store.py` | Deterministic aggregate regime replay; source priority/cutoffs/unknowns/executable breadth. |
| `python/tests/test_observer_campaign_quotes.py` | Exact ENTRY/EXIT arithmetic and fail-closed malformed/wrong-purpose/no-route behavior. |
| `python/tests/test_observer_campaign_risk_context.py` | State-derived exposure/PnL/loss-streak/drawdown/health behavior. |
| `python/tests/test_observer_campaign_assembler.py` | Clean assembly plus future-data, safety, missing-quote, DEAD-regime, attribution, and unsupported-setup failures. |
| `python/tests/test_observer_campaign_runner.py` | First cycle, restart equivalence, replay/idempotence, contradiction/corruption, attribution, and no-promotion/live-authority coverage. |
| `python/tests/test_observer_campaign_public_api.py` | Exact `__all__`, restricted public methods, source-import firewall, and fresh-process authority firewall. |

### Explicitly absent from the E15 behavior diff

No E15 behavior change was made to the sealed strategy/risk/evaluation/promotion/live modules. In particular, the E14->E15 behavior diff contains no modifications that change:

- B1 safety policy thresholds or precedence,
- B2 feature arithmetic,
- B6 regime classifier behavior,
- C5 paper orchestration semantics,
- C6 accounting/checkpoint semantics,
- E11 evaluation normalization,
- E12 proof gates,
- registry mutation/promotion logic,
- live execution, transaction construction, signing, submission, or credentials.

## 5. Point-in-time, purpose, restart, and accounting invariants proven

E15 tests prove the following boundaries:

- future observer, mint-state, market, quote, or regime rows are invisible at an earlier `as_of`;
- ENTRY evidence is never substituted with EXIT evidence and vice versa;
- a missing/unavailable route never becomes a fabricated execution price or synthetic fill;
- malformed, contradictory, or wrongly attributed evidence fails closed;
- B1 `INCOMPLETE` and `REJECT` results pass into the sealed decision path unchanged rather than being upgraded optimistically;
- dynamic risk state is reconstructed from actual paper positions/journal/intent state and explicit health facts;
- uninterrupted execution and process reconstruction converge on equivalent paper state/accounting/evaluation evidence for the tested restart path;
- processed-intent/checkpoint/evidence replay is idempotent only when content matches; collisions or contradictions fail closed;
- E11 evidence corruption fails closed;
- no E15 code auto-invokes E12 promotion or gains live/signing/submission authority.

## 6. Behavior freeze and seal protocol

The immutable E15 behavior head is:

`7deb85a4215f72a97bc473991c53be73050d4bca`

Its full repository CI is run `32885314743`: Python **2225 passed in 8.50s**, Rust GREEN, repository safety GREEN.

This verification record is intentionally the **only file modified after the frozen behavior head** for the E15 seal. The resulting seal commit SHA and its exact-seal CI run are recorded in PR #39 metadata after the commit and CI complete. They cannot be embedded back into this document without creating a second post-seal document mutation and invalidating the one-commit/one-file seal property.

Required mechanical seal proof after this record is committed:

1. behavior head -> seal is exactly one commit;
2. the only changed file is this verification record;
3. exact-seal full CI is GREEN;
4. PR #39 remains draft and unmerged on sealed E14.

## 7. Profitability and live-money boundary

E15 proves campaign machinery, evidence provenance, purpose correctness, restart behavior for the tested path, accounting/evaluation bridging, and authority containment. It does **not** prove that Shreks has positive expectancy or that any strategy should trade real money.

Synthetic fixtures and deterministic tests are correctness evidence, not profitability evidence.

After E15 is sealed, the next proof step is to run the observer-paper campaign on actual point-in-time market/safety data and accumulate real independent paper trades. Those results must flow through the existing E10/E11/E12 evaluation/proof stack and be judged on evidence including:

- net expectancy after realistic costs,
- profit factor,
- maximum drawdown,
- independent trade count,
- distinct token/mint count,
- evidence time span,
- fees/slippage/cost burden,
- winner concentration and dependence on extreme outliers,
- reproducible accounting,
- reproducible evaluation,
- setup/regime performance where statistically meaningful.

Promotion thresholds must not be invented, relaxed, or tuned merely to make the gate pass.

Before Phase F real-money activation, Shreks must also demonstrate stable provider/degradation behavior, restart/recovery stability, realistic fill behavior, reliable risk halts/kill switch, execution/accounting integrity, reconciliation integrity, and paper/live decision-path parity.

**Live trading remains disabled.**
