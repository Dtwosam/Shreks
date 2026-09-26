# Fast PAPER Shadow Quote/USD Source — Design

**Date:** 2026-09-26  
**Base main SHA:** `40315a0f9f3e8bbbd96c065a11a6a5e76cfdee19`

## Purpose

Add a canonical write-once source record for explicit quote-asset/USD conversion
evidence used by learned shadow execution.

This slice does not derive USD values and does not publish an execution-input
source. It only authenticates caller-supplied
`FastPaperShadowQuoteUsdEvidence` against one exact learned decision.

## Record contract

Add schema:

`shreks.fast_paper_shadow_quote_usd_source` version `1`.

Add public:

- `FastPaperShadowQuoteUsdSourceRecord`;
- `build_fast_paper_shadow_quote_usd_source_record(...)`;
- `write_fast_paper_shadow_quote_usd_source_record(...)`;
- `read_fast_paper_shadow_quote_usd_source_record(...)`.

Each record binds:

- runtime manifest fingerprint;
- decision evidence fingerprint;
- source-event id;
- market key;
- decision evaluation timestamp;
- exact quote mint;
- exact `FastPaperShadowQuoteUsdEvidence`;
- deterministic record fingerprint.

## Validation

Building must:

1. require the exact runtime manifest and exact decision evidence types;
2. authenticate release/manifest/champion/action-policy identity against the
   runtime manifest;
3. require quote/USD mint equality with the decision quote mint;
4. require quote/USD observation at or before decision evaluation;
5. require source fingerprint/version/rate validity through the existing
   `FastPaperShadowQuoteUsdEvidence` constructor;
6. never invent, normalize, or look up a USD rate.

The filename is deterministic from the exact decision evidence fingerprint.

The reader must rebuild the expected record from the restored
`FastPaperShadowQuoteUsdEvidence`. Unknown fields, non-canonical JSON,
symlinks, malformed floats, fingerprint mismatch, or decision/manifest drift
fail closed.

## Persistence

Canonical JSON, exactly one trailing newline, mode 0600, write-once publication
into an existing regular non-symlink directory.

## Authority boundary

```text
QUOTE_USD_SOURCE=WRITE_ONCE_AUTHENTICATED
QUOTE_USD_FACTS=EXPLICIT_ONLY
QUOTE_USD_DERIVATION=FORBIDDEN
OBSERVER_DATABASE_ACCESS=NOT_GRANTED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
EXECUTION_SOURCE_PUBLICATION=NOT_GRANTED
SHADOW_EXECUTION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
SCORING_CONTROL_PATH=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
PRODUCTION_PAPER_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- stable public schema/model/build/read/write API;
- exact decision + manifest binding;
- strict quote-mint and chronology validation;
- canonical private write-once round trip;
- stale/tamper/symlink refusal;
- no observer/provider/network, scoring, execution-source publication,
  execution, signing/submission, or LIVE authority.
