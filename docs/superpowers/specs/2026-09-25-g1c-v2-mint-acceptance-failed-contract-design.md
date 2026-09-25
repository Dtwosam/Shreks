# G1C V2 Mint-State Acceptance FAILED Contract Design

**Date:** 2026-09-25  
**Branch:** `fix/g1c-v2-mint-acceptance-failed-contract`  
**Base / deployed release:** `a583e3617af266fb6e09d6d8b33dc1a80826a443`

## Production evidence

The exact sealed selection-only replay release
`a583e3617af266fb6e09d6d8b33dc1a80826a443` deployed successfully.

The protected verifier reached the mint-state acceptance bridge and completed
quickly rather than timing out, but then terminated with:

```text
mint acceptance failure shape is invalid
```

The control contract has two distinct ways to produce top-level
`status="FAILED"`:

1. an operational/control failure returned by `_failure_result`, which carries
   an `error={code,message}` object;
2. a completed behavioral acceptance analysis whose own result is
   `status="FAILED"`, which carries `analysis` plus validated
   `runtime_status`.

The verifier currently assumes every top-level `FAILED` is case (1), so it
rejects a legitimate behavioral failure before printing its bounded evidence.

## Goal

Preserve both failure meanings without weakening fail-closed behavior:

- operational failure: validate the bounded error object, surface only the
  allowlisted code/sanitized message, and exit terminally;
- behavioral acceptance failure: validate the complete analysis and runtime
  status exactly like PASS/HOLD, print the bounded counters, report physical
  acceptance FAILED, and exit terminally.

## Internal verifier protocol

The embedded Python validator may use an internal-only sentinel
`CONTROL_FAILED` for operational failures so the surrounding shell can
distinguish them from a completed behavioral `FAILED` analysis.

The external log remains:

```text
g1c_v2_mint_state_acceptance_status=FAILED
```

for either terminal failure type.

Behavioral FAILED must additionally surface only the same bounded counters used
for PASS/HOLD:

- selected observations;
- proactive refreshes;
- selected missing mint rows;
- selected stale mint rows;
- invalid observations;
- reconstructed checkpoints;
- maximum selected mint age;
- PAPER-evidence completed cycles/provider failures;
- Helius attempted/limit/remaining/budget-exhausted.

No candidate IDs, mints, raw database values, SQL, paths, or exception details
are added.

## RED / GREEN plan

RED requires the workflow to:

1. accept `FAILED` as a valid analysis status when an `analysis` object is
   present;
2. distinguish operational failures from behavioral failures internally;
3. print bounded analysis counters before terminal exit for behavioral FAILED;
4. retain terminal exit for both failure classes;
5. preserve HOLD as non-terminal and PASS as success.

GREEN is workflow/test-only. No runtime Python trading or evidence semantics
change.

## Non-authority

```text
MINT_ACCEPTANCE_ANALYSIS=UNCHANGED
CANDIDATE_SELECTION=UNCHANGED
HISTORICAL_REPLAY=UNCHANGED
SAFETY_POLICY=UNCHANGED
REGIME_POLICY=UNCHANGED
SETUP_POLICY=UNCHANGED
SCORING_POLICY=UNCHANGED
RISK_POLICY=UNCHANGED
PAPER_EXECUTION=UNCHANGED
MODEL_CHAMPION_AUTHORITY=UNCHANGED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
