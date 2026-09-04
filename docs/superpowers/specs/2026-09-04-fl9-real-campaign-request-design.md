# FL9 Canonical Real Campaign Request — Design

**Date:** 2026-09-04

## Status

Implementation slice after immutable deterministic campaign artifact merge
`d2150420440c642fded88e51de4a228ea91e73dc` (#193).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Make the sealed deterministic campaign artifact runnable from one durable request file instead of Python object setup.

The request layer does not add campaign logic. It converts one authenticated canonical request into the exact existing objects required by #193.

## Request schema

Schema:

`shreks.fast_deterministic_campaign_request` v1.

The request contains:

- observer database path;
- FL8.1 feature Parquet path;
- comparison catalog path;
- authenticated champion path;
- FL3 entry-authority binary path;
- deterministic candidate binary path;
- destination path;
- exact comparison execution policy;
- one exact point-in-time context per FL8.1 row;
- PAPER run-id prefix;
- assessment version;
- starting PAPER cash;
- starting ledger clock;
- exact PAPER fill policy;
- exact risk policy;
- exact position-action policy;
- exact trading-evaluation policy;
- request fingerprint.

Paths are stored as strings and resolved relative to the request file directory unless absolute.

## Typed canonical serialization

The codec uses a fixed local registry of approved dataclasses and enums.

Supported values are only:

- `None`;
- bool;
- int;
- str;
- finite float encoded as `{"$float":"<hex>"}`;
- tuple encoded with `$tuple`;
- frozenset encoded with `$frozenset` and canonical ordering;
- approved enum encoded with `$enum`;
- approved dataclass encoded with `$type` + exact field set.

No arbitrary dictionaries, class paths, dynamic imports, pickle, or executable deserialization are accepted.

Raw JSON floats and arrays are rejected inside request values.

The full request JSON must be byte-equivalent canonical compact sorted-key JSON.

## Request fingerprint

Fingerprint material contains:

- schema name;
- schema version;
- the complete encoded request body.

The fingerprint excludes only itself.

The builder computes it.

The encoder recomputes it before emitting.

The decoder reconstructs the exact typed object and recomputes the same fingerprint before accepting.

## Single-capital invariant

One proof run has one starting capital.

Therefore:

`evaluation_policy.starting_equity_usd == starting_cash_usd`

and every:

`context.risk_environment.trading_capital_usd == starting_cash_usd`.

This prevents PAPER accounting, risk sizing, and evaluation percentages from using different account sizes.

## File runner

`run_fast_deterministic_campaign_request_file(...)`:

1. reads and authenticates the canonical request;
2. resolves all paths relative to the request file;
3. requires every source path to identify an existing file;
4. reads the sealed FL8.1 Parquet population;
5. requires context count == FL8.1 row count;
6. requires starting ledger time <= earliest FL8.1 decision;
7. decodes the exact comparison catalog;
8. creates a fresh empty PAPER ledger from explicit starting cash/time;
9. delegates exactly to `write_fast_deterministic_campaign_artifact(...)`.

The destination remains immutable under the #193 writer.

## Authority boundary

The request module has no:

- provider/network calls;
- dynamic code loading;
- superiority evaluation;
- model selection;
- signing/submission;
- LIVE authority.

It only loads local evidence/configuration and calls the sealed deterministic campaign artifact writer.

## TDD

Intentional RED:

`8df0f374ba86b7bd88944ca967e6d74d04d52082`.

Tests require:

1. exact typed request round trip;
2. canonical JSON;
3. tagged float/frozenset/enum evidence;
4. noncanonical rejection;
5. raw-float rejection;
6. fingerprint tamper rejection;
7. unknown type rejection;
8. capital/equity mismatch rejection;
9. relative path resolution;
10. sealed feature/catalog reads;
11. fresh common PAPER ledger creation;
12. exact delegation to #193;
13. source authority firewall.

## Following slice

Add a tiny console entry point that accepts exactly one request-file path and invokes this runner.

After that, the engineering path is ready for a real non-fixture campaign execution.
