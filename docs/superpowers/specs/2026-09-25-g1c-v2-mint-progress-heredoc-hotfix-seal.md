# G1C V2 Mint Progress Verifier Heredoc Hotfix Seal

**Date:** 2026-09-25  
**Integration SHA:** `933397eae42901446fa9565e52eebb96f37412df`  
**PR:** #499  
**Merged-main CI:** `36125601293`

## Production failure

The sealed mint-state analysis-progress release
`dad327f7e7b050efd3103fd9c04cccd1b32ee530` installed successfully and left
the PAPER runtime healthy, but the production verifier terminated with:

```text
bash: line 1439: syntax error: unexpected end of file
```

The failure was verifier syntax only. The Python heredoc used to validate
`progress.json` was indented two spaces farther than the workflow block's
working nested heredocs. After YAML block dedent, Bash therefore saw an
indented closing `PY` marker and never terminated that heredoc.

## Sealed fix

The progress-validation heredoc body and closing `PY` marker now use the same
YAML indentation pattern as the already-working mint-result validation heredoc.

No command, field validation, progress stage, acceptance rule, timeout, runtime
configuration, or trading behavior changed.

## Regression proof

The integration suite now extracts the exact remote production Bash body from
`.github/workflows/verify-production-paper.yml`, removes the YAML block
indentation, and requires:

```text
bash -n
```

to succeed.

This validates the full remote verifier shell, including nested heredocs,
before another production seal is released.

## RED / GREEN evidence

RED head:
`83c8081062fda25b5ddb8f7b2f72d2bb0e3a6f66`

CI run `36124945608`:

- Python tests: FAIL exactly on
  `test_production_verifier_remote_script_is_valid_bash`;
- parser error: `line 1439: syntax error: unexpected end of file`;
- Rust tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

GREEN head:
`9a724f9319258736b145b24b47394b3c4e1ded38`

CI run `36125257006`:

- Python tests: PASS;
- Rust tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

Merged integration SHA:
`933397eae42901446fa9565e52eebb96f37412df`

Merged-main CI run `36125601293`:

- Python tests: PASS;
- Rust tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

## Physical follow-up

Release and deploy this exact seal, then run the existing production verifier.

The verifier must either:

- produce the existing PASS/HOLD/FAILED acceptance result; or
- retain terminal TIMEOUT behavior while printing the sanitized mint-analysis
  progress stage/timestamp.

No timeout increase or analyzer/strategy change is authorized by this hotfix.

## Explicit non-authority

```text
VERIFIER_LOGIC=UNCHANGED_EXCEPT_HEREDOC_ALIGNMENT
VERIFIER_TIMEOUT_SECONDS=180_UNCHANGED
MINT_PROGRESS_SCHEMA=UNCHANGED
MINT_PROGRESS_STAGE_ENUM=UNCHANGED
HISTORICAL_ANALYZER=UNCHANGED
B1_MAX_CRITICAL_DATA_AGE_MS=UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=UNCHANGED
DATABASE_PERMISSIONS=UNCHANGED
SUDO_AUTHORITY=UNCHANGED
OBSERVATION_AUTHORITY=READ_ONLY
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
