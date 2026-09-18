# Automatic PAPER Deploy Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically continue a successful canonical sealed release into protected PAPER deployment and production verification without manual workflow dispatch.

**Architecture:** Keep immutable release creation, deployment, and verification as separate authority layers. Extend deploy with a provenance-bound `workflow_run` trigger plus a non-secret resolve job, make the verifier reusable through `workflow_call`, and call it only after deployment succeeds while retaining manual fallback paths.

**Tech Stack:** GitHub Actions YAML, Bash, GitHub CLI, Python static delivery tests.

**Spec:** `docs/superpowers/specs/2026-09-18-auto-paper-deploy-chain-design.md`

## Global Constraints

- GitHub remains the source/test/release/deployment control plane; the VPS remains the continuously running host.
- Release creation remains isolated from production secrets.
- Automatic deploy is eligible only from a successful `Build sealed Shreks release` run whose own event is `workflow_run`.
- Manual deploy and manual production verification remain supported.
- `production-paper` environment protections remain intact.
- No sudoers, release-manager, systemd, protected-state permission, wallet/signing/submission, PAPER promotion, or LIVE authority changes.
- `V2_SCORING_RETRY=NOT_YET_AUTHORIZED`.
- `PAPER_PROMOTION=BLOCKED`.
- `LIVE=DISABLED`.

---

### Task 1: Define automatic deployment and reusable-verifier contracts

**Files:**
- Modify: `python/tests/test_g2_delivery_workflows.py`
- Test: `python/tests/test_g2_delivery_workflows.py`

**Interfaces:**
- Consumes: current release/deploy/verify workflow text.
- Produces: static RED contracts for automatic release provenance, resolve outputs, immutable release verification, reusable verifier invocation, and preserved authority boundaries.

- [ ] **Step 1: Replace manual-only deploy assertions with dual-trigger assertions**

Require the deploy workflow to contain:

```python
assert "workflow_dispatch:" in workflow
assert "workflow_run:" in workflow
assert 'workflows: ["Build sealed Shreks release"]' in workflow
assert "github.event.workflow_run.conclusion == 'success'" in workflow
assert "github.event.workflow_run.event == 'workflow_run'" in workflow
assert "source_sha" in workflow
assert "release_tag" in workflow
```

Keep exact manual tag syntax and `contents: read`.

- [ ] **Step 2: Add immutable-release provenance assertions**

Require pre-host-contact verification text including:

```python
for required in (
    "gh api",
    ".immutable",
    ".target_commitish",
    ".draft",
    ".prerelease",
    "shreks-$SOURCE_SHA",
):
    assert required in workflow
```

Require that release validation appears before the first SSH/SCP host-contact command.

- [ ] **Step 3: Add reusable verifier assertions**

Require `verify-production-paper.yml` to contain both:

```python
assert "workflow_dispatch:" in workflow
assert "workflow_call:" in workflow
```

Require deploy to contain:

```python
assert "uses: ./.github/workflows/verify-production-paper.yml" in workflow
assert "needs: [resolve, deploy]" in workflow
assert "expected_release_sha:" in workflow
assert "secrets: inherit" in workflow
```

- [ ] **Step 4: Preserve negative authority assertions**

Continue proving no new secret names, no wallet/provider/live values, no sudo/systemd commands in the verifier, no protected-state mutation, and no deployment secret consumption in release workflow.

- [ ] **Step 5: Run Python delivery tests and capture RED**

Run:

```bash
python -m pytest python/tests/test_g2_delivery_workflows.py -q
```

Expected: failures specifically because deploy lacks `workflow_run`/resolve/reusable-verifier wiring and verifier lacks `workflow_call`.

- [ ] **Step 6: Commit RED tests**

```bash
git add python/tests/test_g2_delivery_workflows.py
git commit -m "test: define automatic PAPER deploy chain"
```

---

### Task 2: Make production verifier reusable without changing verification behavior

**Files:**
- Modify: `.github/workflows/verify-production-paper.yml`
- Test: `python/tests/test_g2_delivery_workflows.py`

**Interfaces:**
- Consumes: `expected_release_sha: string`, `journal_minutes: string`.
- Produces: the existing `verify` job callable from either manual dispatch or another workflow.

- [ ] **Step 1: Add `workflow_call` inputs matching manual inputs**

Use:

```yaml
on:
  workflow_dispatch:
    inputs:
      expected_release_sha:
        description: Expected active sealed 40-character source commit
        required: true
        type: string
      journal_minutes:
        description: Read-only journal lookback window in minutes
        required: true
        default: "30"
        type: string
  workflow_call:
    inputs:
      expected_release_sha:
        required: true
        type: string
      journal_minutes:
        required: false
        default: "30"
        type: string
```

- [ ] **Step 2: Keep the verifier environment and transport boundary unchanged**

Retain:

```yaml
permissions:
  contents: read

jobs:
  verify:
    environment: production-paper
```

Do not change the SSH, service-health, journal, historical-read, or FL9 discovery logic.

- [ ] **Step 3: Normalize input access**

Use the common `inputs` context:

```yaml
env:
  EXPECTED_RELEASE_SHA: ${{ inputs.expected_release_sha }}
  JOURNAL_MINUTES: ${{ inputs.journal_minutes }}
```

- [ ] **Step 4: Run focused delivery tests**

Run:

```bash
python -m pytest python/tests/test_g2_delivery_workflows.py -q
```

Expected: reusable-verifier assertions pass; deploy-chain assertions remain RED.

- [ ] **Step 5: Commit verifier change**

```bash
git add .github/workflows/verify-production-paper.yml
git commit -m "feat: make production PAPER verifier reusable"
```

---

### Task 3: Add automatic deploy provenance, immutable release verification, and chained verifier

**Files:**
- Modify: `.github/workflows/deploy.yml`
- Test: `python/tests/test_g2_delivery_workflows.py`

**Interfaces:**
- Consumes automatic event `github.event.workflow_run.head_sha` or manual `inputs.release_tag`.
- Produces `needs.resolve.outputs.source_sha` and `needs.resolve.outputs.release_tag`.
- Calls reusable verifier with exact deployed SHA only after deployment success.

- [ ] **Step 1: Add automatic workflow trigger**

Use:

```yaml
on:
  workflow_dispatch:
    inputs:
      release_tag:
        description: Existing immutable release tag shreks-<40-char-sha>
        required: true
        type: string
  workflow_run:
    workflows: ["Build sealed Shreks release"]
    types: [completed]
    branches: [main]
```

- [ ] **Step 2: Add fail-closed resolve job**

Create `jobs.resolve` with outputs:

```yaml
outputs:
  source_sha: ${{ steps.resolve.outputs.source_sha }}
  release_tag: ${{ steps.resolve.outputs.release_tag }}
```

Its shell logic must:

```bash
if [[ "$GITHUB_EVENT_NAME" == "workflow_run" ]]; then
  [[ "$RELEASE_RUN_CONCLUSION" == "success" ]] || exit 1
  [[ "$RELEASE_RUN_EVENT" == "workflow_run" ]] || exit 1
  SOURCE_SHA="$RELEASE_RUN_HEAD_SHA"
  [[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || exit 2
  RELEASE_TAG="shreks-$SOURCE_SHA"
else
  RELEASE_TAG="$MANUAL_RELEASE_TAG"
  [[ "$RELEASE_TAG" =~ ^shreks-[0-9a-f]{40}$ ]] || exit 2
  SOURCE_SHA="${RELEASE_TAG#shreks-}"
fi
printf 'source_sha=%s\n' "$SOURCE_SHA" >> "$GITHUB_OUTPUT"
printf 'release_tag=%s\n' "$RELEASE_TAG" >> "$GITHUB_OUTPUT"
```

- [ ] **Step 3: Bind deploy job to resolve outputs and production environment**

Use:

```yaml
deploy:
  needs: resolve
  environment: production-paper
  env:
    SOURCE_SHA: ${{ needs.resolve.outputs.source_sha }}
    RELEASE_TAG: ${{ needs.resolve.outputs.release_tag }}
```

Remove duplicate tag parsing from the deploy job.

- [ ] **Step 4: Verify immutable release object before asset download or host contact**

Before download, run:

```bash
gh api "repos/$GITHUB_REPOSITORY/releases/tags/$RELEASE_TAG" > "$RUNNER_TEMP/shreks-release.json"
python - "$RUNNER_TEMP/shreks-release.json" "$RELEASE_TAG" "$SOURCE_SHA" <<'PY'
import json
import sys

path, expected_tag, expected_sha = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    release = json.load(handle)
if release.get("tag_name") != expected_tag:
    raise SystemExit("release tag mismatch")
if release.get("target_commitish") != expected_sha:
    raise SystemExit("release target mismatch")
if release.get("draft") is not False or release.get("prerelease") is not False:
    raise SystemExit("release is not production-shaped")
if release.get("immutable") is not True:
    raise SystemExit("release is not immutable")
names = sorted(asset.get("name") for asset in release.get("assets", []))
expected = sorted([
    "RELEASE_MANIFEST.json",
    f"shreks-release-{expected_sha}.tar.gz",
    f"shreks-release-{expected_sha}.tar.gz.sha256",
])
if names != expected:
    raise SystemExit("release asset set mismatch")
PY
```

Only after this passes may `gh release download`, SSH, or SCP execute.

- [ ] **Step 5: Invoke reusable verifier only after deploy success**

Add:

```yaml
verify:
  needs: [resolve, deploy]
  uses: ./.github/workflows/verify-production-paper.yml
  with:
    expected_release_sha: ${{ needs.resolve.outputs.source_sha }}
    journal_minutes: "30"
  secrets: inherit
```

- [ ] **Step 6: Run focused delivery tests**

Run:

```bash
python -m pytest python/tests/test_g2_delivery_workflows.py -q
```

Expected: GREEN.

- [ ] **Step 7: Commit deploy chain**

```bash
git add .github/workflows/deploy.yml
git commit -m "feat: auto-deploy sealed PAPER releases"
```

---

### Task 4: Document automatic chain and run full gates

**Files:**
- Modify: `deploy/release/README.md`
- Test: `python/tests/test_g2_delivery_workflows.py`

**Interfaces:**
- Consumes: implemented automatic release/deploy/verify chain.
- Produces: durable operator documentation and full verification evidence.

- [ ] **Step 1: Document normal automatic path and manual fallbacks**

Add a runbook section containing:

```text
seal merge -> CI -> immutable release -> PAPER deploy -> production verify -> protected FL9 discovery
```

State that `production-paper` environment protection remains authoritative and manual deploy/verify remain fallback controls.

- [ ] **Step 2: Document fail-closed provenance checks**

Record that automatic deploy only accepts successful canonical automatic release runs and independently verifies release immutability, exact target SHA, and exact asset set before host contact.

- [ ] **Step 3: Add/adjust runbook static assertions**

Require the new automatic-chain text while preserving the existing narrow-deploy-account and LIVE-disabled assertions.

- [ ] **Step 4: Run focused Python tests**

Run:

```bash
python -m pytest python/tests/test_g2_delivery_workflows.py -q
```

Expected: GREEN.

- [ ] **Step 5: Run full canonical CI locally where available and then GitHub CI**

Required repository gates:

```text
Repository safety
Python tests
Rust tests
ARM64 release build
```

All must be green on the exact feature head.

- [ ] **Step 6: Review diff for authority creep**

Confirm no changes to:

```text
deploy/release/release_manager.py
deploy/systemd/
sudoers instructions
wallet/signing/submission code
promotion authority
LIVE authority
```

- [ ] **Step 7: Commit documentation**

```bash
git add deploy/release/README.md python/tests/test_g2_delivery_workflows.py
git commit -m "docs: document automatic PAPER deploy chain"
```
