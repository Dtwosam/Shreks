# G1C V2 Mint Progress Verifier Heredoc Hotfix Design

**Date:** 2026-09-25  
**Branch:** `fix/g1c-v2-mint-progress-heredoc`  
**Base / deployed release:** `dad327f7e7b050efd3103fd9c04cccd1b32ee530`

## Production failure

The exact progress-diagnostics release installed successfully, but production
verification terminated before the acceptance timeout/result path could finish:

```text
bash: line 1439: syntax error: unexpected end of file
```

The defect is confined to the verifier source. The Python heredoc used to
validate `progress.json` is indented two spaces farther than the surrounding
workflow block. YAML removes the workflow block's common indentation, leaving
the heredoc body and closing `PY` marker indented in the actual Bash script.
Bash therefore does not recognize the terminator and reaches EOF.

## Fix

Move the progress-validation heredoc body and closing `PY` marker left by two
spaces so they use the same YAML indentation pattern as the already-working
mint-result validation heredoc.

No command, validation condition, accepted progress field, stage enum, timeout,
or authority changes.

## Regression proof

Add a repository test that:

1. extracts the remote Bash body from
   `.github/workflows/verify-production-paper.yml`;
2. removes the YAML block indentation exactly as Actions does;
3. runs `bash -n` over the resulting remote script;
4. requires a zero exit status.

This catches malformed nested heredocs before another sealed production deploy.

## Explicit non-authority

```text
VERIFIER_LOGIC=UNCHANGED_EXCEPT_SYNTAX
VERIFIER_TIMEOUT_SECONDS=180_UNCHANGED
MINT_PROGRESS_SCHEMA=UNCHANGED
MINT_PROGRESS_STAGE_ENUM=UNCHANGED
HISTORICAL_ANALYZER=UNCHANGED
B1_MAX_CRITICAL_DATA_AGE_MS=UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=UNCHANGED
DATABASE_PERMISSIONS=UNCHANGED
SUDO_AUTHORITY=UNCHANGED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
