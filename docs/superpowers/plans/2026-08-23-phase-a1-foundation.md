# Shreks Phase A1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a tested Rust + Python repository foundation for Shreks with shared runtime-mode semantics, secret-safe configuration scaffolding, CI, and clear local commands.

**Architecture:** Keep the repository as one codebase with a Rust workspace for Solana-facing components and a Python package for the trading brain. Phase A1 introduces no provider integrations or strategy logic; it only creates the stable project skeleton and a tiny cross-language runtime-mode contract that later phases can depend on.

**Tech Stack:** Rust 2021 workspace, Python 3.12+, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-23-shreks-master-design.md`

## Global Constraints

- Solana only for V1.
- Rust + Python architecture.
- Free external data/API/RPC sources only for V1.
- Never commit wallet private keys, seed phrases, or live secrets.
- Paper trading precedes live trading.
- Runtime modes are exactly: `observe`, `paper`, `shadow`, `live`, `halted`.
- No provider, database, strategy, or live-execution code is introduced in Phase A1.

---

### Task 1: Repository safety and workspace scaffolding

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `Cargo.toml`
- Create: `crates/shreks-core/Cargo.toml`
- Create: `python/pyproject.toml`
- Create: `python/src/shreks_brain/__init__.py`

**Interfaces:**
- Produces the Rust workspace root and Python package root used by every later task.
- Defines placeholder runtime environment names only; no real secrets.

- [ ] **Step 1: Create secret-safe ignore rules**

Ignore `.env`, `.env.*` except `.env.example`, Python caches/venvs, Rust `target/`, SQLite runtime databases, Parquet output, IDE artifacts, and OS junk.

- [ ] **Step 2: Create `.env.example`**

Include placeholder names for `SHREKS_MODE`, `SHREKS_DB_PATH`, `SHREKS_LOG_LEVEL`, `SOLANA_RPC_URL`, `HELIUS_API_KEY`, `DEXSCREENER_BASE_URL`, and `JUPITER_BASE_URL`. Default `SHREKS_MODE=observe`. Do not include a wallet secret variable in Phase A1.

- [ ] **Step 3: Create Rust workspace metadata**

Workspace member: `crates/shreks-core`. Use resolver `2` and edition `2021` in the crate.

- [ ] **Step 4: Create Python package metadata**

Package name `shreks-brain`, Python `>=3.12`, source root `python/src`, pytest as the only Phase A1 dev dependency.

- [ ] **Step 5: Verify scaffold parses**

Run: `cargo metadata --no-deps --format-version 1`
Expected: exit 0.

Run: `python -m pip install -e 'python[dev]'`
Expected: editable install succeeds.

---

### Task 2: Rust runtime-mode contract using TDD

**Files:**
- Test: `crates/shreks-core/tests/runtime_mode.rs`
- Create: `crates/shreks-core/src/lib.rs`

**Interfaces:**
- Produces: `shreks_core::RuntimeMode` implementing `Default`, `Display`, and `FromStr`.
- Valid strings: `observe`, `paper`, `shadow`, `live`, `halted`.
- Default: `RuntimeMode::Observe`.
- Invalid strings return a descriptive error and never silently fall back.

- [ ] **Step 1: Write the failing Rust tests**

Tests assert all five strings parse, display round-trips, default is observe, and an unknown string fails.

- [ ] **Step 2: Run tests and verify RED**

Run: `cargo test -p shreks-core`
Expected: compile/test failure because `RuntimeMode` is not implemented.

- [ ] **Step 3: Implement minimal `RuntimeMode`**

Use an enum plus a small `ParseRuntimeModeError` type. Do not add environment loading yet.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `cargo test -p shreks-core`
Expected: all runtime-mode tests pass.

---

### Task 3: Python runtime-mode contract using TDD

**Files:**
- Test: `python/tests/test_runtime_mode.py`
- Create: `python/src/shreks_brain/runtime.py`

**Interfaces:**
- Produces: `shreks_brain.runtime.RuntimeMode` as a string enum.
- Produces: `parse_runtime_mode(value: str | None) -> RuntimeMode`.
- `None` maps to `OBSERVE`; invalid text raises `ValueError`.

- [ ] **Step 1: Write the failing Python tests**

Tests cover all five valid strings, default-on-None, and invalid-value rejection.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest python/tests -q`
Expected: import failure because runtime module is not implemented.

- [ ] **Step 3: Implement minimal runtime-mode code**

Use only the Python standard library (`enum.StrEnum`).

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest python/tests -q`
Expected: all tests pass.

---

### Task 4: CI and operator documentation

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

**Interfaces:**
- CI executes the same Rust and Python test commands used locally.
- README explains project purpose, architecture, current phase, safe setup, and exact test commands.

- [ ] **Step 1: Add CI**

On pushes and pull requests, run one Rust job (`cargo test --workspace`) and one Python 3.12 job (`pip install -e 'python[dev]'`, then `pytest python/tests -q`).

- [ ] **Step 2: Replace placeholder README**

Document that Shreks is currently in Phase A and live trading is disabled. Include setup/test commands and a warning never to commit secrets.

- [ ] **Step 3: Verify all checks locally**

Run: `cargo test --workspace`
Expected: pass.

Run: `python -m pytest python/tests -q`
Expected: pass.

Run: `git grep -n -E '(PRIVATE_KEY|SEED_PHRASE|SECRET_KEY)=' -- ':!docs/**' ':!.env.example'`
Expected: no committed secret assignments.

---

## Completion Gate

Phase A1 is complete only when:

1. Rust workspace metadata parses.
2. Rust tests pass.
3. Python editable installation succeeds.
4. Python tests pass.
5. CI mirrors local verification.
6. `.env` and runtime databases are ignored.
7. No provider integration, strategy logic, or live-wallet secret handling has leaked into the foundation.
