# Fast PAPER Shadow Candidate Attribution — Design

**Date:** 2026-09-26  
**Base main SHA:** `40315a0f9f3e8bbbd96c065a11a6a5e76cfdee19`

## Purpose

Extract the Fast PAPER shadow service's existing private observer-candidate
attribution query into one reusable, read-only runtime API.

Decision production already proves candidate identity from the exact persisted
ENTRY quote probe identity. Future execution-source publishers also need that
same candidate identity to bind point-in-time external evidence without
inventing or selecting a different candidate.

This slice moves no execution authority. It only seals candidate attribution.

## Public contract

Add:

- `FastPaperShadowCandidateAttributionRequest`;
- `resolve_fast_paper_shadow_candidate_id(...)`.

The immutable request carries only:

- base mint;
- quote mint;
- decision observation timestamp;
- evaluation timestamp;
- probe-policy version;
- taker;
- slippage bps;
- ENTRY input amount raw;
- maximum quote age.

The runtime manifest remains authoritative for:

- observer database path;
- quote provider;
- quote mint.

The request quote mint must equal the manifest quote mint.

## Resolution

The resolver must reproduce the existing service query exactly:

1. open the manifest observer database read-only with SQLite URI `mode=ro`;
2. require query-only mode;
3. compute:
   `earliest = max(decision_observed_at, evaluated_at - max_quote_age_ms)`;
4. join `paper_quote_snapshots` to `token_candidates`;
5. require:
   - exact mint;
   - `purpose='entry'`;
   - manifest quote provider;
   - exact probe-policy version;
   - manifest/request quote mint as input mint;
   - base mint as output mint;
   - exact taker;
   - exact canonical raw input amount;
   - exact slippage;
   - quote timestamp within the decision/evaluation window;
6. collect distinct candidate ids;
7. require exactly one positive candidate id.

Missing or ambiguous attribution fails closed.

## Service integration

The decision service must construct one exact attribution request from:

- the feature row;
- the authenticated service policy;
- the chosen evaluation timestamp;

then call the public resolver.

The old private `_resolve_candidate_id` function is removed.

The service still owns no execution, USD valuation, source publication, or
provider-network authority.

## Replay suitability

For persisted learned decision evidence:

- `evidence.as_of_unix_ms` is already required to equal the source feature
  row's `decision_observed_at_unix_ms`;
- `evidence.evaluated_at_unix_ms` preserves the decision evaluation boundary.

Therefore a later bounded publisher can reconstruct the same attribution
request using authenticated decision evidence plus the same service-policy
probe identity.

This slice does not yet perform that later USD read.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
CANDIDATE_ATTRIBUTION=READ_ONLY
OBSERVER_DATABASE=QUERY_ONLY
QUOTE_PROVIDER_AUTHORITY=MANIFEST_ONLY
QUOTE_MINT_AUTHORITY=MANIFEST_ONLY
USD_VALUATION=NOT_GRANTED
EXECUTION_SOURCE_PUBLICATION=NOT_GRANTED
SHADOW_EXECUTION=NOT_GRANTED
SHADOW_LEDGER_MUTATION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
PRODUCTION_PAPER_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- public immutable attribution request;
- public resolver;
- exact persisted ENTRY quote identity query;
- deterministic unique-candidate resolution;
- missing/ambiguous fail-closed behavior;
- query-only observer DB access;
- manifest quote-provider/quote-mint binding;
- service delegation through the public API;
- no scoring, USD valuation, source publication, execution, provider/network,
  signing/submission, or LIVE authority.
