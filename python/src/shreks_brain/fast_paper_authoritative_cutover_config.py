from __future__ import annotations

import math
from pathlib import Path
import re
from typing import Mapping

from .fast_paper_runtime.authoritative_runtime import (
    FastPaperAuthoritativeRuntimeConfig,
    load_fast_paper_authoritative_runtime_config,
)
from .fast_paper_runtime.models import FastPaperRuntimeManifest


class FastPaperAuthoritativeCutoverConfigError(RuntimeError):
    pass


_ENV_KEYS = (
    "SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH",
    "SHREKS_FAST_PAPER_SERVICE_POLICY_PATH",
    "SHREKS_FAST_PAPER_DECISION_EVIDENCE_DIRECTORY",
    "SHREKS_FAST_PAPER_INTERVAL_SECONDS",
    "SHREKS_FAST_PAPER_AUTHORITATIVE_EXECUTION_POLICY_PATH",
    "SHREKS_FAST_PAPER_AUTHORITATIVE_EXECUTION_SOURCE_DIRECTORY",
    "SHREKS_FAST_PAPER_AUTHORITATIVE_DATABASE_PATH",
    "SHREKS_FAST_PAPER_AUTHORITATIVE_RUN_ID",
    "SHREKS_FAST_PAPER_BUY_AUTHORITY_SOURCE_DIRECTORY",
    "SHREKS_FAST_PAPER_QUOTE_USD_SOURCE_DIRECTORY",
    "SHREKS_FAST_PAPER_REDUCTION_SOURCE_DIRECTORY",
    "SHREKS_FAST_PAPER_PENDING_BUY_RETRY_SOURCE_DIRECTORY",
)
_STATIC_PRODUCTION_VALUES = {
    "SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH": (
        "/etc/shreks/fast-paper-runtime-manifest.json"
    ),
    "SHREKS_FAST_PAPER_SERVICE_POLICY_PATH": (
        "/etc/shreks/fast-paper-shadow-service-policy.json"
    ),
    "SHREKS_FAST_PAPER_DECISION_EVIDENCE_DIRECTORY": (
        "/var/lib/shreks/fast-paper-authoritative/decision"
    ),
    "SHREKS_FAST_PAPER_INTERVAL_SECONDS": "2.0",
    "SHREKS_FAST_PAPER_AUTHORITATIVE_EXECUTION_POLICY_PATH": (
        "/etc/shreks/fast-paper-shadow-execution-policy.json"
    ),
    "SHREKS_FAST_PAPER_AUTHORITATIVE_EXECUTION_SOURCE_DIRECTORY": (
        "/var/lib/shreks/fast-paper-authoritative/execution-sources"
    ),
    "SHREKS_FAST_PAPER_BUY_AUTHORITY_SOURCE_DIRECTORY": (
        "/var/lib/shreks/fast-paper-authoritative/buy-authority-sources"
    ),
    "SHREKS_FAST_PAPER_QUOTE_USD_SOURCE_DIRECTORY": (
        "/var/lib/shreks/fast-paper-authoritative/quote-usd-sources"
    ),
    "SHREKS_FAST_PAPER_REDUCTION_SOURCE_DIRECTORY": (
        "/var/lib/shreks/fast-paper-authoritative/reduction-sources"
    ),
    "SHREKS_FAST_PAPER_PENDING_BUY_RETRY_SOURCE_DIRECTORY": (
        "/var/lib/shreks/fast-paper-authoritative/pending-buy-retry-sources"
    ),
}
_KEY_RE = re.compile(r"^[A-Z0-9_]+$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SHELL_FORBIDDEN = (
    "$",
    "`",
    '"',
    "'",
    "\\",
    ";",
    "&",
    "|",
    "<",
    ">",
    "(",
    ")",
    "\x00",
)


def read_fast_paper_authoritative_cutover_environment(
    path: str | Path,
) -> dict[str, str]:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise FastPaperAuthoritativeCutoverConfigError(
            "authoritative cutover environment must be a regular non-symlink file"
        )
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FastPaperAuthoritativeCutoverConfigError(
            "authoritative cutover environment is unreadable"
        ) from exc
    result: dict[str, str] = {}
    for line_number, raw in enumerate(text.splitlines(), start=1):
        if not raw or raw.startswith("#"):
            continue
        if raw.strip() != raw or "=" not in raw or raw.startswith("export "):
            raise FastPaperAuthoritativeCutoverConfigError(
                f"authoritative cutover environment line {line_number} is invalid"
            )
        key, value = raw.split("=", 1)
        if (
            _KEY_RE.fullmatch(key) is None
            or not value
            or value != value.strip()
            or any(token in value for token in _SHELL_FORBIDDEN)
            or any(character.isspace() for character in value)
        ):
            raise FastPaperAuthoritativeCutoverConfigError(
                f"authoritative cutover environment line {line_number} is invalid"
            )
        if key in result:
            raise FastPaperAuthoritativeCutoverConfigError(
                f"duplicate authoritative cutover environment key: {key}"
            )
        result[key] = value
    _require_exact_keys(result)
    return result


def encode_fast_paper_authoritative_cutover_environment(
    environment: Mapping[str, str],
) -> str:
    if not isinstance(environment, Mapping):
        raise FastPaperAuthoritativeCutoverConfigError(
            "authoritative cutover environment must be a mapping"
        )
    env = dict(environment)
    _require_exact_keys(env)
    for key in _ENV_KEYS:
        value = env[key]
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or any(token in value for token in _SHELL_FORBIDDEN)
            or any(character.isspace() for character in value)
        ):
            raise FastPaperAuthoritativeCutoverConfigError(
                f"authoritative cutover environment value is invalid: {key}"
            )
    return "".join(f"{key}={env[key]}\n" for key in _ENV_KEYS)


def validate_fast_paper_authoritative_cutover_environment(
    environment: Mapping[str, str],
    manifest: FastPaperRuntimeManifest,
    *,
    authoritative_database_path: str | Path,
) -> FastPaperAuthoritativeRuntimeConfig:
    if not isinstance(environment, Mapping):
        raise FastPaperAuthoritativeCutoverConfigError(
            "authoritative cutover environment must be a mapping"
        )
    if type(manifest) is not FastPaperRuntimeManifest:
        raise FastPaperAuthoritativeCutoverConfigError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    env = dict(environment)
    _require_exact_keys(env)
    for key, expected in _STATIC_PRODUCTION_VALUES.items():
        if env[key] != expected:
            raise FastPaperAuthoritativeCutoverConfigError(
                f"authoritative cutover production path mismatch: {key}"
            )

    database = Path(authoritative_database_path).expanduser().resolve(
        strict=False
    )
    manifest_database = Path(manifest.observer_database_path).expanduser().resolve(
        strict=False
    )
    configured_database = Path(
        env["SHREKS_FAST_PAPER_AUTHORITATIVE_DATABASE_PATH"]
    ).expanduser().resolve(strict=False)
    if database != manifest_database or configured_database != database:
        raise FastPaperAuthoritativeCutoverConfigError(
            "authoritative database must exactly equal the manifest observer database"
        )

    run_id = env["SHREKS_FAST_PAPER_AUTHORITATIVE_RUN_ID"]
    if (
        _RUN_ID_RE.fullmatch(run_id) is None
        or run_id.lower().startswith("replace-with")
        or "placeholder" in run_id.lower()
    ):
        raise FastPaperAuthoritativeCutoverConfigError(
            "authoritative Fast PAPER run id must be explicit non-placeholder text"
        )

    try:
        interval = float(env["SHREKS_FAST_PAPER_INTERVAL_SECONDS"])
    except ValueError as exc:
        raise FastPaperAuthoritativeCutoverConfigError(
            "authoritative Fast PAPER interval is invalid"
        ) from exc
    if not math.isfinite(interval) or interval != 2.0:
        raise FastPaperAuthoritativeCutoverConfigError(
            "authoritative Fast PAPER interval must be exactly 2.0 seconds"
        )

    try:
        config = load_fast_paper_authoritative_runtime_config(env)
    except Exception as exc:
        raise FastPaperAuthoritativeCutoverConfigError(
            "authoritative cutover environment is incompatible with runtime configuration"
        ) from exc
    return config


def _require_exact_keys(environment: Mapping[str, str]) -> None:
    if set(environment) != set(_ENV_KEYS):
        raise FastPaperAuthoritativeCutoverConfigError(
            "authoritative cutover environment key set must be exact"
        )
