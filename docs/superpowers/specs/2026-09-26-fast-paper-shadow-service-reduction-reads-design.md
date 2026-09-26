# Fast PAPER Shadow Service Explicit Reduction Reads — Design

**Date:** 2026-09-26  
**Base main SHA:** `99eb59d409dcd66357aed3b4d238e809f2c59bbc`

## Purpose

Allow the supervised learned decision service to consume explicit
target-specific persisted REDUCE quote read authority without deriving raw token
amounts from normalized PAPER holdings.

Partial Fast PAPER fills are allowed and the isolated ledger stores normalized
float quantity, not original raw token units. Therefore the service must not
invent a float-to-raw rounding rule.

## Contract

Extend `run_fast_paper_shadow_service_cycle(...)` with optional:

`reduction_read_resolver(record, position) -> tuple[FastPaperShadowReductionRead, ...]`

Semantics:

- `None` preserves the existing empty reduction-read behavior exactly;
- when supplied, the resolver is called once per feature row after posture
  resolution and before quote resolution;
- the return must be a tuple containing only exact
  `FastPaperShadowReductionRead` values;
- FLAT posture may not carry reduction reads;
- OPEN posture may carry explicit reads, which are passed unchanged into
  `FastPaperShadowQuoteReadPolicy`;
- resolver failure or malformed authority fails the cycle closed before learned
  decision persistence.

This hook only authenticates caller-supplied raw quote-read identity. It does
not claim those raw amounts are derivable from the PAPER ledger.

## Authority boundary

```text
RAW_REDUCTION_AMOUNT_DERIVATION=FORBIDDEN
REDUCTION_READ_AUTHORITY=EXPLICIT_CALLER_ONLY
DEFAULT_REDUCTION_READS=EMPTY_UNCHANGED
OBSERVER_QUOTES=READ_ONLY
SHADOW_LEDGER_READ=NOT_ADDED
SHADOW_EXECUTION=NOT_ADDED
SCORING_CONTROL_PATH=FORBIDDEN
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- optional reduction-read resolver keyword;
- default empty compatibility;
- exact OPEN reduction-read propagation;
- FLAT non-empty refusal;
- malformed/resolver-error fail closed;
- no raw-unit derivation, ledger mutation, execution, scoring, provider network,
  cutover, or LIVE authority.

Current main is expected to fail because the service cycle does not accept the
new resolver keyword.
