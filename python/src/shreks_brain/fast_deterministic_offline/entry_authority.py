from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from shreks_brain.fast_campaign_paper import FastCampaignPaperEntryAuthority
from shreks_brain.research.fast_training_features import FastTrainingFeatureRecord

from .models import (
    FastOfflineEntryExecution,
    FastOfflineExecutionLegCost,
)


FAST_DETERMINISTIC_ENTRY_AUTHORITY_REQUEST_SCHEMA_NAME = (
    "shreks.fast_deterministic_entry_authority_request"
)
FAST_DETERMINISTIC_ENTRY_AUTHORITY_REQUEST_SCHEMA_VERSION = 1
FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_NAME = (
    "shreks.fast_deterministic_entry_authority_result"
)
FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_VERSION = 1

_RESULT_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "mint",
        "quote_mint",
        "intended_base_quantity",
        "decision_executable_entry_price_quote",
        "maximum_acceptable_entry_price_quote",
        "expected_entry_variable_cost_bps",
        "expected_entry_fixed_cost_quote",
        "result_fingerprint_sha256",
    }
)


def derive_fast_deterministic_entry_authority_offline(
    *,
    binary_path: str | Path,
    record: FastTrainingFeatureRecord,
    execution: FastOfflineEntryExecution,
) -> FastCampaignPaperEntryAuthority | None:
    if type(record) is not FastTrainingFeatureRecord:
        raise ValueError("record must be exact FastTrainingFeatureRecord")
    if type(execution) is not FastOfflineEntryExecution:
        raise ValueError("execution must be exact FastOfflineEntryExecution")
    if (
        execution.trade.executable_entry_price_quote
        != record.decision_executable_entry_price_quote
    ):
        raise ValueError(
            "execution decision price provenance does not match FL8.1 record"
        )

    binary = Path(binary_path)
    if not str(binary).strip() or not binary.is_file():
        raise ValueError("binary_path must identify an existing file")

    request = {
        "schema_name": FAST_DETERMINISTIC_ENTRY_AUTHORITY_REQUEST_SCHEMA_NAME,
        "schema_version": FAST_DETERMINISTIC_ENTRY_AUTHORITY_REQUEST_SCHEMA_VERSION,
        "mint": record.mint,
        "quote_mint": record.quote_mint,
        "decision_executable_entry_price_quote": (
            record.decision_executable_entry_price_quote
        ),
        "execution": _execution_to_wire(execution),
    }
    request_payload = _canonical(request)

    request_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="shreks-fast-entry-authority-",
            suffix=".json",
            delete=False,
        ) as handle:
            handle.write(request_payload)
            request_path = Path(handle.name)

        completed = subprocess.run(
            [str(binary), str(request_path)],
            shell=False,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            stderr = completed.stderr[-2_000:].strip()
            detail = f": {stderr}" if stderr else ""
            raise RuntimeError(
                "offline deterministic entry authority exited "
                f"{completed.returncode}{detail}"
            )
        if not completed.stdout:
            raise RuntimeError(
                "offline deterministic entry authority returned empty stdout"
            )
        return _decode_result(
            completed.stdout,
            record=record,
            execution=execution,
        )
    finally:
        if request_path is not None:
            request_path.unlink(missing_ok=True)


def _decode_result(
    payload: str,
    *,
    record: FastTrainingFeatureRecord,
    execution: FastOfflineEntryExecution,
) -> FastCampaignPaperEntryAuthority | None:
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "deterministic entry authority result is malformed JSON"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError(
            "deterministic entry authority result must be a JSON object"
        )
    actual_keys = frozenset(document)
    if actual_keys != _RESULT_KEYS:
        raise ValueError(
            "deterministic entry authority result has unknown or missing fields"
        )

    claimed = document["result_fingerprint_sha256"]
    _require_sha256("result_fingerprint_sha256", claimed)
    material = dict(document)
    material.pop("result_fingerprint_sha256")
    expected = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    if claimed != expected:
        raise ValueError(
            "deterministic entry authority result fingerprint mismatch"
        )

    if document["schema_name"] != FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_NAME:
        raise ValueError(
            "unsupported deterministic entry authority result schema_name"
        )
    if (
        document["schema_version"]
        != FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_VERSION
    ):
        raise ValueError(
            "unsupported deterministic entry authority result schema_version"
        )
    if document["mint"] != record.mint or document["quote_mint"] != record.quote_mint:
        raise ValueError(
            "deterministic entry authority market identity mismatch"
        )
    if (
        document["decision_executable_entry_price_quote"]
        != record.decision_executable_entry_price_quote
    ):
        raise ValueError(
            "deterministic entry authority decision price mismatch"
        )
    if document["intended_base_quantity"] != execution.trade.base_quantity:
        raise ValueError(
            "deterministic entry authority intended quantity mismatch"
        )

    expected_variable = _entry_variable_cost_bps(execution.cost_model.entry)
    expected_fixed = _entry_fixed_cost_quote(execution.cost_model.entry)
    if document["expected_entry_variable_cost_bps"] != expected_variable:
        raise ValueError(
            "deterministic entry authority variable cost mismatch"
        )
    if document["expected_entry_fixed_cost_quote"] != expected_fixed:
        raise ValueError(
            "deterministic entry authority fixed cost mismatch"
        )

    maximum = document["maximum_acceptable_entry_price_quote"]
    if (
        isinstance(maximum, bool)
        or not isinstance(maximum, (int, float))
        or not float(maximum) > 0.0
    ):
        raise ValueError(
            "deterministic entry authority maximum entry price is invalid"
        )

    # FL3 can truthfully derive a positive maximum that is already below the
    # decision price. In that case FL6 must SKIP and there is no PAPER BUY
    # authority to construct.
    if float(maximum) < record.decision_executable_entry_price_quote:
        return None

    return FastCampaignPaperEntryAuthority(
        mint=record.mint,
        quote_mint=record.quote_mint,
        intended_base_quantity=execution.trade.base_quantity,
        decision_executable_entry_price_quote=(
            record.decision_executable_entry_price_quote
        ),
        maximum_acceptable_entry_price_quote=float(maximum),
        expected_entry_variable_cost_bps=expected_variable,
        expected_entry_fixed_cost_quote=expected_fixed,
    )


def _execution_to_wire(value: FastOfflineEntryExecution) -> dict[str, object]:
    return {
        "cost_model": {
            "version": value.cost_model.version,
            "entry": _leg_to_wire(value.cost_model.entry),
            "exit": _leg_to_wire(value.cost_model.exit),
        },
        "trade": {
            "base_quantity": value.trade.base_quantity,
            "executable_entry_price_quote": (
                value.trade.executable_entry_price_quote
            ),
            "forecast_exit_price_quote": value.trade.forecast_exit_price_quote,
            "exit_capacity_base": value.trade.exit_capacity_base,
            "required_edge_bps": value.trade.required_edge_bps,
            "risk_margin_bps": value.trade.risk_margin_bps,
        },
    }


def _leg_to_wire(value: FastOfflineExecutionLegCost) -> dict[str, object]:
    return {
        "effective_fee_bps": value.effective_fee_bps,
        "expected_impact_bps": value.expected_impact_bps,
        "expected_slippage_bps": value.expected_slippage_bps,
        "expected_latency_bps": value.expected_latency_bps,
        "network_fee_quote": value.network_fee_quote,
        "priority_fee_quote": value.priority_fee_quote,
        "expected_failure_cost_quote": value.expected_failure_cost_quote,
    }


def _entry_variable_cost_bps(value: FastOfflineExecutionLegCost) -> int:
    return (
        value.effective_fee_bps
        + value.expected_impact_bps
        + value.expected_slippage_bps
        + value.expected_latency_bps
    )


def _entry_fixed_cost_quote(value: FastOfflineExecutionLegCost) -> float:
    return (
        value.network_fee_quote
        + value.priority_fee_quote
        + value.expected_failure_cost_quote
    )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
