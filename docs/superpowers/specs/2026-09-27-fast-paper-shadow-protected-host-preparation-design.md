# Fast PAPER Shadow Protected Host Preparation — Design

**Date:** 2026-09-27  
**Base main SHA:** `b762c31b1a05100da074c3377386b5bb96ec822b`

## Purpose

Complete the protected host-preparation boundary immediately before any
production shadow service activation.

The repository already contains:

- the sealed shadow systemd unit and env template;
- exact-release trusted-admin unit installation;
- an explicit isolated shadow provisioner;
- supervisor preflight that authenticates the learned runtime and isolated
  execution state.

What is still missing is one safe production ceremony that binds those pieces
to the actual host ownership model.

The service runs as `shreks:shreks`. Therefore initial shadow state must be
created by that service identity, not by root, or the private `0700` state
roots would become unwritable to the service.

This slice adds only protected configuration installation, service-identity
state provisioning, and read-only host readiness proof.

It does not reload systemd, start/enable/restart/stop the shadow service, join
`shreks.target`, replace legacy PAPER authority, sign/submit, or enable LIVE.

## CLI

Add one release-local CLI:

```text
shreks-fast-paper-shadow-host-prepare authority-preflight <expected-release-sha> <candidate-authority-dir>
shreks-fast-paper-shadow-host-prepare install-authority <expected-release-sha> <candidate-authority-dir>
shreks-fast-paper-shadow-host-prepare config-preflight <expected-release-sha> <candidate-env>
shreks-fast-paper-shadow-host-prepare install-config <expected-release-sha> <candidate-env>
shreks-fast-paper-shadow-host-prepare provision-state <expected-release-sha>
shreks-fast-paper-shadow-host-prepare host-preflight <expected-release-sha>
```

The first, second, and fourth commands require root.

`provision-state` must reject root and require the exact `shreks` service
uid/gid.

## Protected authority bundle

Before the env/state steps, the trusted administrator supplies one private
candidate directory containing exactly:

```text
fast-paper-runtime-manifest.json
fast-paper-shadow-service-policy.json
fast-paper-shadow-execution-policy.json
fast-paper-shadow-buy-writer-policy.json
```

The host-preparation CLI must authenticate these with the existing canonical
runtime readers and binding verifiers before any publication:

- runtime manifest canonical decode and fingerprint;
- runtime manifest `release_source_sha` equals the explicit active release;
- champion artifact plus decision/feature binary hashes and identities verify;
- service policy canonical decode and route-evidence version matches manifest;
- execution policy canonical decode/bindings against the manifest;
- buy-writer policy canonical decode and exact manifest/service-policy binding.

`authority-preflight` is read-only. `install-authority` may publish only the
four fixed destinations under `/etc/shreks`, each as `root:shreks 0640`.

Publication is no-replace and idempotent. A mixed exact/absent state may be
completed; any divergent bytes, symlink, wrong metadata, unsafe parent, invalid
candidate member set, failed binding, or release swap fails closed.

The authority installer does not generate, tune, or modify policy content. It
only authenticates and publishes operator-supplied canonical artifacts whose
existing bindings already prove their champion/release identity.

## Protected env contract

The candidate env file is data, not a shell script.

Parsing rules:

- UTF-8 only;
- blank lines and full-line comments allowed;
- every non-comment line is exactly `KEY=VALUE`;
- no `export`, shell expansion, command substitution, quotes, continuation,
  NUL, duplicate keys, or whitespace around names;
- the key set is exact and closed.

Required keys are exactly the existing supervised/provisioned shadow runtime
settings:

- `SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH`;
- `SHREKS_FAST_PAPER_SHADOW_SERVICE_POLICY_PATH`;
- `SHREKS_FAST_PAPER_SHADOW_EVIDENCE_DIRECTORY`;
- `SHREKS_FAST_PAPER_SHADOW_INTERVAL_SECONDS`;
- `SHREKS_FAST_PAPER_SHADOW_MAXIMUM_DECISIONS`;
- `SHREKS_FAST_PAPER_SHADOW_EXECUTION_POLICY_PATH`;
- `SHREKS_FAST_PAPER_SHADOW_EXECUTION_SOURCE_DIRECTORY`;
- `SHREKS_FAST_PAPER_SHADOW_LEDGER_DATABASE_PATH`;
- `SHREKS_FAST_PAPER_SHADOW_LEDGER_RUN_ID`;
- `SHREKS_FAST_PAPER_SHADOW_BUY_WRITER_POLICY_PATH`;
- `SHREKS_FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_DIRECTORY`;
- `SHREKS_FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_DIRECTORY`;
- `SHREKS_FAST_PAPER_SHADOW_REDUCTION_SOURCE_DIRECTORY`;
- `SHREKS_FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_DIRECTORY`;
- `SHREKS_FAST_PAPER_SHADOW_STARTING_CASH_USD`.

The parsed document is validated through the existing
`load_fast_paper_shadow_provision_config(...)` contract.

Production path shape is fixed:

```text
/etc/shreks/fast-paper-runtime-manifest.json
/etc/shreks/fast-paper-shadow-service-policy.json
/etc/shreks/fast-paper-shadow-execution-policy.json
/etc/shreks/fast-paper-shadow-buy-writer-policy.json

/var/lib/shreks/fast-paper-shadow/decision
/var/lib/shreks/fast-paper-shadow/execution-sources
/var/lib/shreks/fast-paper-shadow/buy-authority-sources
/var/lib/shreks/fast-paper-shadow/quote-usd-sources
/var/lib/shreks/fast-paper-shadow/reduction-sources
/var/lib/shreks/fast-paper-shadow/pending-buy-retry-sources
/var/lib/shreks/fast-paper-shadow/ledger.sqlite3
```

The run id must be non-placeholder trimmed text.

The config destination is fixed:

```text
/etc/shreks/fast-paper-shadow.env
```

It is installed no-replace/idempotently as `root:shreks 0640` so the trusted
service-identity provision step can authenticate the same configuration the
unit will consume.

## Exact-release binding

Every command authenticates the explicit expected SHA against
`/opt/shreks/current` and requires execution from that release's
`.venv/bin`.

Root commands additionally require the previously commissioned unit to be exact
and already installed.

No command may select a release by freshness.

## Config installation

`config-preflight` is read-only and reports either:

- `READY_TO_INSTALL_CONFIG`;
- `READY_CONFIG_ALREADY_INSTALLED`.

`install-config` may publish only
`/etc/shreks/fast-paper-shadow.env`.

Publication is same-directory, fsynced, root:shreks `0640`, hard-link
no-replace, idempotent for exact bytes, and fail-closed for drift, symlinks,
wrong metadata, unsafe parents, or release swap.

It does not create any runtime state.

## Service-identity state provisioning

`provision-state`:

1. requires effective uid/gid equal the resolved `shreks` identity;
2. authenticates the exact active release/runtime executable;
3. reads the installed env only if it is exact root:shreks `0640`;
4. re-validates the production env shape;
5. requires `/var/lib/shreks/fast-paper-shadow` already exist as
   `shreks:shreks 0700`;
6. invokes the existing `provision_fast_paper_shadow(...)`;
7. verifies all dedicated source/evidence leaf directories are
   `shreks:shreks 0700`;
8. verifies the isolated ledger is `shreks:shreks 0600`;
9. emits a canonical self-fingerprinted receipt.

The root shadow directory is intentionally created outside this CLI by the
trusted administrator with an explicit bounded host action:

```text
install -d -o shreks -g shreks -m 0700 /var/lib/shreks/fast-paper-shadow
```

The existing provisioner remains the only ledger/runtime-state initializer.

## Host preflight

`host-preflight` is root-only and read-only.

It requires:

- exact active release and runtime executable;
- exact previously installed shadow unit;
- exact protected env bytes/metadata and production path shape;
- the four protected shadow authority files exist as regular non-symlink
  `root:shreks 0640` files;
- root shadow state directory and all configured source/evidence directories are
  `shreks:shreks 0700`;
- isolated ledger is `shreks:shreks 0600`;
- existing supervisor bootstrap succeeds using the installed config;
- `shreks.target` still does not contain the shadow unit.

The successful receipt reports:

`state=READY_FOR_DORMANT_SYSTEMD_LOAD_REVIEW`

while explicitly retaining:

- `daemon_reload_authority=NOT_GRANTED`;
- `service_start_authority=NOT_GRANTED`;
- `paper_cutover_authority=NOT_GRANTED`;
- `signing_submission_authority=NOT_GRANTED`;
- `live_authority=DISABLED`.

## Authority firewall

The new host-preparation source must contain no:

- subprocess;
- systemctl;
- daemon-reload;
- service start/enable/restart/stop;
- scoring;
- provider/network client;
- wallet/private-key access;
- signing/submission;
- authoritative PAPER ledger mutation;
- LIVE mode.

The only trading-state mutation is delegated to the already-sealed isolated
shadow provisioner, and only from the `shreks` service identity.

## RED acceptance

Tests must prove:

1. exact authority-bundle membership and canonical cross-binding are required;
2. authority publication is fixed-destination, no-replace, metadata-exact, and idempotent;
3. strict env parsing rejects shell syntax, duplicates, unknown/missing keys,
   and placeholders;
4. production path shape is exact;
5. config preflight/install authenticate the exact release and unit;
6. config publication is no-replace, metadata-exact, and idempotent;
7. root cannot run state provisioning;
8. wrong service uid/gid cannot run state provisioning;
9. service-identity provisioning reuses the existing provisioner and verifies
   owner/mode of created state;
10. host preflight is read-only and fails on authority/config/state ownership
   drift;
11. CLI is packaged in the release;
12. source contains no service activation/capital authority;
13. `shreks.target` and release-manager activation logic remain unchanged.

## Following slice

After protected host preparation proves READY on the physical VPS, add the
separate systemd load/start shadow-commissioning proof:

- one explicit daemon reload;
- one explicit start of the detached shadow unit only;
- no enable and no target membership;
- bounded observation window;
- process/release provenance;
- restart counters;
- supervisor status/evidence advancement;
- CPU/RAM/storage/network headroom;
- restart reconstruction evidence.

Only that later slice may grant a one-time shadow-service start authority.
