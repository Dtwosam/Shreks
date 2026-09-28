# Fast Lane FL11.4 Promotion-Readiness Proof — Design

**Date:** 2026-09-28
**Phase:** FL11.4 — Champion/challenger promotion
**Authority:** read-only proof only; no promotion mutation

## Purpose

Add the first FL11.4 boundary for the current learned Fast Lane PAPER-shadow path.

The proof answers one question: does one exact Fast Lane champion have a complete, internally consistent FL11.1/FL11.2a/FL11.2b/FL11.3 evidence chain that satisfies an explicit versioned promotion policy?

The proof is deliberately not the mutation that replaces an approved runtime champion. It cannot change a runtime manifest, replace a champion file, change PAPER authority, sign/submit transactions, or enable LIVE.

This separation is required because the existing generic E8 promotion registry predates the Fast Lane champion artifact and does not provide a proven atomic identity transition for the current FastForecastChampionArtifact.

## Inputs

The command consumes the exact Fast PAPER runtime manifest, expected release source SHA, canonical FL11.1 independent-sample proof, canonical FL11.2a trade-economics report, canonical FL11.2b missed-opportunity report, canonical FL11.3 latency proof, and one canonical FL11.4 promotion policy.

The runtime manifest remains the authority for release identity, champion version/fingerprint, action-policy version, and manifest fingerprint. verify_fast_paper_runtime_bindings(...) must authenticate the manifest's immutable runtime bindings, including the champion artifact.

## Evidence-chain binding

All FL11 reports must bind to the same exact release_source_sha, manifest_fingerprint_sha256, champion_version, champion_fingerprint_sha256, action_policy_version, binding_fingerprint_sha256, window_since_unix_ms, and window_until_unix_ms.

FL11.2a, FL11.2b, and FL11.3 must reference the exact FL11.1 report_fingerprint_sha256.

Every input report must use its exact supported schema name/version, be canonical JSON, contain no duplicate keys, carry a valid self-fingerprint, and preserve:
- promotion_authority=NOT_GRANTED
- production_paper_cutover=NOT_GRANTED
- signing_submission_authority=NOT_GRANTED
- live_authority=DISABLED

FL11.1 must say SUFFICIENT_SAMPLE. FL11.3 is a performance gate and must say LATENCY_PROVEN for readiness.

Malformed evidence, schema drift, identity drift, window drift, fingerprint drift, or authority-boundary drift is a hard proof error rather than a performance failure.

## Promotion policy

Schema: shreks.fast_paper_shadow_promotion_policy version 1.

The policy is explicit and versioned. It contains no hidden defaults:
- version
- min_net_expectancy_pct
- min_profit_factor
- max_drawdown_pct
- max_cost_burden_pct
- max_worst_loss_bps
- max_expected_realized_mae_bps
- max_entry_slippage_p95_bps
- max_entry_capital_utilization_p95_pct
- max_missed_opportunity_rate
- max_missed_opportunity_mean_bps

All numeric thresholds are finite. Percentage/fraction fields are range-checked. The policy is canonical JSON with a SHA-256 fingerprint.

## Gates

The readiness proof emits explicit gates:
- FL11_1_SUFFICIENT_SAMPLE
- MIN_NET_EXPECTANCY_PCT
- MIN_PROFIT_FACTOR
- MAX_DRAWDOWN_PCT
- MAX_COST_BURDEN_PCT
- MAX_WORST_LOSS_BPS
- MAX_EXPECTED_REALIZED_MAE_BPS
- MAX_ENTRY_SLIPPAGE_P95_BPS
- MAX_ENTRY_CAPITAL_UTILIZATION_P95_PCT
- MISSED_OPPORTUNITY_EVIDENCE_COMPLETE
- MAX_MISSED_OPPORTUNITY_RATE
- MAX_MISSED_OPPORTUNITY_MEAN_BPS
- FL11_3_LATENCY_PROVEN

Metrics come only from the sealed FL11 reports. Any partially_or_unscorable_skip_count greater than zero fails missed-opportunity completeness. With zero SKIP decisions, missed-opportunity rate and mean are explicit 0.0. Otherwise the fully-scorable aggregates are used. A required unavailable metric fails closed.

## Decision

The report emits only PROMOTION_READY or PROMOTION_NOT_READY.

PROMOTION_READY means only that the exact champion/evidence chain satisfies the supplied FL11.4 policy. It does not itself grant promotion authority.

## Output identity

Schema: shreks.fast_paper_shadow_promotion_readiness version 1.

The output includes policy version/fingerprint; exact release/manifest/champion/action-policy/binding/window identity; exact FL11.1/2a/2b/3 report fingerprints; selected observed metrics; ordered gate results; decision; authority firewall; and report fingerprint.

## Authority firewall

Always:
- promotion_authority=NOT_GRANTED
- production_paper_cutover=NOT_GRANTED
- signing_submission_authority=NOT_GRANTED
- live_authority=DISABLED

The module must not import or call registry mutation APIs, release-manager mutation APIs, PAPER execution/cutover APIs, signing/submission APIs, LIVE execution APIs, or legacy scoring control paths.

## CLI

Command: shreks-fast-paper-shadow-promotion-readiness

Required arguments:
- --manifest-path
- --sample-proof-path
- --trade-economics-path
- --missed-opportunity-path
- --latency-proof-path
- --promotion-policy-path
- --expected-release-sha

Success prints one canonical readiness report to stdout. Failure prints one canonical fail-closed error document to stderr and exits non-zero.

## Acceptance tests

Tests must prove:
- a fully bound passing chain yields PROMOTION_READY;
- a breached economic threshold yields PROMOTION_NOT_READY;
- a non-proven latency report yields PROMOTION_NOT_READY;
- unavailable required metrics fail closed;
- missed-opportunity partial evidence fails readiness;
- report fingerprint drift is rejected;
- cross-report champion/window/binding/sample-fingerprint drift is rejected;
- policy codec/fingerprint is deterministic and rejects unknown fields;
- authority fields never grant promotion/PAPER/LIVE;
- packaging exposes the CLI;
- source contains no legacy scoring import or registry/runtime mutation path.

## Deferred explicit transition

A later FL11.4 slice may implement an explicit audited champion transition only after the repository contains a Fast Lane-native atomic activation contract whose identity semantics match FastForecastChampionArtifact.

This readiness proof must not fake that transition by reusing the older generic E8 registry.
