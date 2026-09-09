# FL9 V2 First Champion — Quiesced Production Code Seal

**Date:** 2026-09-09  
**Implementation main SHA:** `85c40e362b488f26df0a9444d7aec7ef36c4b21b`  
**Status:** SEALED FOR NEW IMMUTABLE RELEASE; PHYSICAL V2 CHAMPION EVIDENCE NOT YET CREATED

## Supersedes prior physical-attempt release

The earlier immutable release:

`shreks-201178765689055a2e819e1a973b9df92a4fb34e`

must **not** be used for the physical V2 first-champion attempt.

That release contains the pre-production design that creates a full SQLite backup before V2 bundle/context hydration. Production evidence showed:

- observer database approximately 35 GB;
- SQLite WAL approximately 405 MB;
- root filesystem approximately 45 GB;
- a second full database copy cannot be created safely on the production host.

The earlier release remains immutable historical evidence but is operationally superseded for this V2 attempt.

## Frozen upstream V2 authority remains unchanged

Physical cohort artifact fingerprint:

`bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`

Accepted identity fingerprint:

`75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b`

TEST unseen-mint identity fingerprint:

`f896c03590a66f4385a01a347039c9dd8a3ab60a4a181e631fa2e838e12ef285`

Feature identity firewall fingerprint:

`e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0`

V2 first-champion policy:

`fl9-v2-first-champion-v1`

Frozen split, horizon, selection timestamp, required five members, natural TEST floor of 40,000 scored rows per target, and unseen-mint TEST floor of 35,000 scored rows per target are unchanged.

## Production database consistency correction

PR #266 replaced the full-copy database snapshot with a fail-closed quiesced live-database consistency gate.

Reviewed GREEN head:

`40aa46346375bba3c0cb3573b7c581561c20a930`

Merged main:

`85c40e362b488f26df0a9444d7aec7ef36c4b21b`

RED CI:

`34351466699`

The RED Python suite failed on the intentionally absent quiescence/data-version contracts.

GREEN PR CI:

`34351617997`

Merged-main CI:

`34352003154`

Both GREEN runs passed:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

### Quiescence contract

Before any V2 database-derived evidence reads:

- `shreks.target` must be `inactive`;
- `shreks-observe.service` must be `inactive`;
- `shreks-paper-evidence.service` must be `inactive`;
- `shreks-paper-campaign.service` must be `inactive`.

All three services are `PartOf=shreks.target`, so production operation deliberately stops the paper target before the evidence command.

### Database immutability proof

The V2 host runner:

1. opens one read-only SQLite sentinel;
2. records `PRAGMA data_version`;
3. runs existing bundle/target readers against the live database path;
4. runs existing context hydration against the same live database path;
5. re-verifies all runtime units are still inactive;
6. rereads `PRAGMA data_version`;
7. fails before model scoring if the value changed.

The sentinel does **not** begin a long-lived read transaction and therefore does not pin WAL pages.

No second SQLite database file is created.

Any committed mutation during the database-read phase fails closed before V2 model scoring.

## Deployment transport correction

PR #265 hardened the protected production-paper deployment workflow after the first sealed release transfer encountered a full `/var/tmp` filesystem.

Merged main:

`8205947c57bacd399a6b761844e589a1b765f7f5`

The corrected workflow:

- serializes production-paper deploys;
- preserves the exact three release filenames required by checksum verification and sudoers;
- reports `/var/tmp` permissions, space, inode state, and stale staging files;
- cleans only exact transport staging files;
- captures SCP failures before workflow exit;
- keeps release-manager failure diagnostics read-only.

This workflow change does not modify release payload bytes or trading authority.

## Authority boundary

This seal authorizes:

- a new immutable ARM64 release;
- protected deployment to `production-paper`;
- generation of release-bound proof inputs;
- one quiesced read-only V2 first-champion evidence attempt.

This seal does **not** authorize:

- learned-vs-deterministic superiority claims;
- PAPER promotion;
- action-policy promotion;
- risk-intent creation;
- registry promotion;
- transaction construction;
- signing/submission;
- LIVE trading.

PAPER promotion remains **BLOCKED**.

LIVE remains **DISABLED**.

## Required physical sequence

After this seal lands on `main`:

1. seal-main CI must pass all four gates;
2. automatic sealed-release workflow must build the exact seal SHA;
3. verify immutable release `shreks-<seal-sha>` and exactly three assets;
4. deploy that exact release using the protected deployment workflow from current `main`;
5. verify `/opt/shreks/current`, release manifest, runtime process identity, and service working directories;
6. ensure sufficient filesystem headroom without deleting `/var/lib/shreks`;
7. stop the paper runtime:
   `sudo systemctl stop shreks.target`;
8. verify the target plus all three runtime services report `inactive`;
9. generate a new proof workspace using the exact deployed release SHA and sealed proof tools;
10. verify the existing physical V2 cohort artifact still reads back to:
    `bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`;
11. choose a new immutable V2 evidence destination;
12. create a canonical V2 host request binding:
    - deployed release SHA;
    - new proof workspace;
    - observer database;
    - exact cohort artifact;
    - hydration-policy fingerprint;
    - training-economics overlay fingerprint;
    - execution-cost policy fingerprint;
    - evidence destination;
13. execute:
    `sudo /opt/shreks/current/.venv/bin/shreks-fl9-v2-first-champion <request-path>`;
14. read back the final immutable V2 evidence artifact;
15. restart the production paper target after the command exits:
    `sudo systemctl start shreks.target`;
16. verify all runtime processes again resolve to the deployed immutable release;
17. freeze exact artifact fingerprints/counts before inspecting model/economic metrics.

If the V2 command fails, preserve any request/input artifacts, do not overwrite a final evidence destination, restart the paper target, and investigate before retry.

## Physical completion boundary

A later physical evidence seal may claim completion only if evidence proves:

```text
deployed_release_identity=PASS
database_quiescence=PASS
database_data_version_stable=PASS
physical_cohort_fingerprint_verified=YES
bundle_identity_reconciliation=PASS
v2_generalization_members=5
natural_test_floor_per_target=PASS
unseen_mint_test_floor_per_target=PASS
runtime_compatible_champion=CREATED_AND_VERIFIED
v2_evidence_artifact=CREATED_AND_VERIFIED
paper_runtime_restored=PASS
paper_promotion=BLOCKED
live_trading=DISABLED
```

No physical champion/model result is accepted by this code seal.
