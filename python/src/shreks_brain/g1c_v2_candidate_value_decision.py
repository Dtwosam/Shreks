from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from shreks_brain.g1c_v2_entry_sizing_proposal import (
    G1CV2EntrySizingProposalError,
    decode_g1c_v2_entry_sizing_proposal,
)


_SCHEMA_NAME = "shreks.g1c_v2_candidate_value_decision"
_SCHEMA_VERSION = 1
_STATUS_APPROVED = "CANDIDATE_VALUE_APPROVED"
_STATUS_REJECTED = "CANDIDATE_VALUE_REJECTED"
_ACCEPT = "ACCEPT_PROPOSAL"
_REJECT = "REJECT_PROPOSAL"
_REPLACE = "REPLACE_PROPOSAL"
_VALID_DECISIONS = {_ACCEPT, _REJECT, _REPLACE}
_REQUIRED_EVIDENCE_AUTHORITY = "MULTI_REFERENCE_REVIEW"
_VALUE_AUTHORITY = "EXPLICIT_PRODUCTION_DECISION_BOUND"
_NOT_GRANTED = "NOT_GRANTED"
_BLOCKED = "BLOCKED"
_DISABLED = "DISABLED"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_U64 = 2**64 - 1


class G1CV2CandidateValueDecisionError(ValueError):
    """Raised when a candidate-value decision cannot be authenticated safely."""


def decide_g1c_v2_candidate_value(
    *,
    sizing_proposal_path: str | Path,
    decision: str,
    decision_reason: str,
    replacement_entry_input_amount: int | None,
    destination: str | Path,
) -> dict[str, object]:
    proposal_path = _resolve_existing_regular_file(
        sizing_proposal_path,
        label="entry sizing proposal",
    )
    proposal_payload = _read_regular_file_stable(
        proposal_path,
        label="entry sizing proposal",
    )
    try:
        proposal = decode_g1c_v2_entry_sizing_proposal(
            proposal_payload.decode("utf-8")
        )
    except (
        G1CV2EntrySizingProposalError,
        UnicodeDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2CandidateValueDecisionError(
            f"entry sizing proposal authentication failed: {error}"
        ) from error

    if proposal["quote_evidence_authority"] != _REQUIRED_EVIDENCE_AUTHORITY:
        raise G1CV2CandidateValueDecisionError(
            "candidate value decision requires MULTI_REFERENCE_REVIEW "
            "proposal provenance"
        )

    if decision not in _VALID_DECISIONS:
        raise G1CV2CandidateValueDecisionError(
            "candidate value decision is unsupported"
        )
    _require_non_empty_text("decision_reason", decision_reason)

    proposed_amount = proposal["proposed_entry_input_amount"]
    _require_positive_u64("proposed_entry_input_amount", proposed_amount)

    if decision == _ACCEPT:
        if replacement_entry_input_amount is not None:
            raise G1CV2CandidateValueDecisionError(
                "ACCEPT_PROPOSAL forbids a replacement entry amount"
            )
        status = _STATUS_APPROVED
        selected_amount: int | None = proposed_amount
        value_authority = _VALUE_AUTHORITY
    elif decision == _REPLACE:
        if replacement_entry_input_amount is None:
            raise G1CV2CandidateValueDecisionError(
                "REPLACE_PROPOSAL requires a replacement entry amount"
            )
        _require_positive_u64(
            "replacement_entry_input_amount",
            replacement_entry_input_amount,
        )
        if replacement_entry_input_amount == proposed_amount:
            raise G1CV2CandidateValueDecisionError(
                "replacement entry amount must differ from proposal"
            )
        status = _STATUS_APPROVED
        selected_amount = replacement_entry_input_amount
        value_authority = _VALUE_AUTHORITY
    else:
        if replacement_entry_input_amount is not None:
            raise G1CV2CandidateValueDecisionError(
                "REJECT_PROPOSAL forbids a replacement entry amount"
            )
        status = _STATUS_REJECTED
        selected_amount = None
        value_authority = _NOT_GRANTED

    proposal_after = _read_regular_file_stable(
        proposal_path,
        label="entry sizing proposal",
    )
    if proposal_after != proposal_payload:
        raise G1CV2CandidateValueDecisionError(
            "entry sizing proposal changed while decision was derived"
        )

    material: dict[str, object] = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": status,
        "decision": decision,
        "decision_reason": decision_reason,
        "source_proposal_sha256": hashlib.sha256(
            proposal_payload
        ).hexdigest(),
        "proposal_fingerprint_sha256": proposal[
            "proposal_fingerprint_sha256"
        ],
        "source_manifest_sha256": proposal["source_manifest_sha256"],
        "source_runtime_manifest_fingerprint_sha256": proposal[
            "source_runtime_manifest_fingerprint_sha256"
        ],
        "source_paper_run_id": proposal["source_paper_run_id"],
        "target_quote_mint": proposal["target_quote_mint"],
        "target_quote_decimals": proposal["target_quote_decimals"],
        "target_quote_usd_per_token": proposal[
            "target_quote_usd_per_token"
        ],
        "quote_evidence_fingerprint_sha256": proposal[
            "quote_evidence_fingerprint_sha256"
        ],
        "quote_evidence_observed_at_unix_ms": proposal[
            "quote_evidence_observed_at_unix_ms"
        ],
        "quote_evidence_authority": proposal["quote_evidence_authority"],
        "proposed_entry_input_amount": proposed_amount,
        "selected_entry_input_amount": selected_amount,
        "candidate_value_authority": value_authority,
        "candidate_authoring_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    result = {
        **material,
        "decision_fingerprint_sha256": _sha256_canonical(material),
    }
    _write_once(destination, result)
    written = Path(destination).expanduser().resolve()
    verified = decode_g1c_v2_candidate_value_decision(
        written.read_text(encoding="utf-8")
    )
    if verified != result:
        raise G1CV2CandidateValueDecisionError(
            "written candidate value decision did not round-trip"
        )
    return result


def decode_g1c_v2_candidate_value_decision(
    payload: str,
) -> dict[str, object]:
    document = _decode_canonical_text(payload)
    expected_keys = {
        "schema_name",
        "schema_version",
        "status",
        "decision",
        "decision_reason",
        "source_proposal_sha256",
        "proposal_fingerprint_sha256",
        "source_manifest_sha256",
        "source_runtime_manifest_fingerprint_sha256",
        "source_paper_run_id",
        "target_quote_mint",
        "target_quote_decimals",
        "target_quote_usd_per_token",
        "quote_evidence_fingerprint_sha256",
        "quote_evidence_observed_at_unix_ms",
        "quote_evidence_authority",
        "proposed_entry_input_amount",
        "selected_entry_input_amount",
        "candidate_value_authority",
        "candidate_authoring_authority",
        "rotation_authority",
        "scoring_authority",
        "paper_promotion_authority",
        "live_authority",
        "decision_fingerprint_sha256",
    }
    if set(document) != expected_keys:
        raise G1CV2CandidateValueDecisionError(
            "candidate value decision has unknown or missing fields"
        )

    static_values = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "quote_evidence_authority": _REQUIRED_EVIDENCE_AUTHORITY,
        "candidate_authoring_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    for name, expected in static_values.items():
        if document.get(name) != expected:
            raise G1CV2CandidateValueDecisionError(
                f"candidate value decision {name} is unsupported"
            )

    decision = document.get("decision")
    if decision not in _VALID_DECISIONS:
        raise G1CV2CandidateValueDecisionError(
            "candidate value decision is unsupported"
        )
    _require_non_empty_text("decision_reason", document.get("decision_reason"))

    for name in (
        "source_proposal_sha256",
        "proposal_fingerprint_sha256",
        "source_manifest_sha256",
        "source_runtime_manifest_fingerprint_sha256",
        "quote_evidence_fingerprint_sha256",
        "decision_fingerprint_sha256",
    ):
        _require_sha256(name, document.get(name))

    for name in (
        "source_paper_run_id",
        "target_quote_mint",
    ):
        _require_non_empty_text(name, document.get(name))
    _require_decimals(
        "target_quote_decimals",
        document.get("target_quote_decimals"),
    )
    _parse_positive_decimal(
        "target_quote_usd_per_token",
        document.get("target_quote_usd_per_token"),
    )
    _require_non_negative_int(
        "quote_evidence_observed_at_unix_ms",
        document.get("quote_evidence_observed_at_unix_ms"),
    )
    _require_positive_u64(
        "proposed_entry_input_amount",
        document.get("proposed_entry_input_amount"),
    )

    selected = document.get("selected_entry_input_amount")
    status = document.get("status")
    value_authority = document.get("candidate_value_authority")
    proposed = document["proposed_entry_input_amount"]

    if decision == _ACCEPT:
        if status != _STATUS_APPROVED or value_authority != _VALUE_AUTHORITY:
            raise G1CV2CandidateValueDecisionError(
                "accepted proposal authority/status is inconsistent"
            )
        _require_positive_u64("selected_entry_input_amount", selected)
        if selected != proposed:
            raise G1CV2CandidateValueDecisionError(
                "accepted proposal must select the proposed entry amount"
            )
    elif decision == _REPLACE:
        if status != _STATUS_APPROVED or value_authority != _VALUE_AUTHORITY:
            raise G1CV2CandidateValueDecisionError(
                "replacement proposal authority/status is inconsistent"
            )
        _require_positive_u64("selected_entry_input_amount", selected)
        if selected == proposed:
            raise G1CV2CandidateValueDecisionError(
                "replacement entry amount must differ from proposal"
            )
    else:
        if status != _STATUS_REJECTED or value_authority != _NOT_GRANTED:
            raise G1CV2CandidateValueDecisionError(
                "rejected proposal authority/status is inconsistent"
            )
        if selected is not None:
            raise G1CV2CandidateValueDecisionError(
                "rejected proposal must not select an entry amount"
            )

    claimed = document["decision_fingerprint_sha256"]
    material = dict(document)
    del material["decision_fingerprint_sha256"]
    if _sha256_canonical(material) != claimed:
        raise G1CV2CandidateValueDecisionError(
            "candidate value decision fingerprint mismatch"
        )
    return document


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2CandidateValueDecisionError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise G1CV2CandidateValueDecisionError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise G1CV2CandidateValueDecisionError(
            f"{label} could not be resolved"
        ) from error


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise G1CV2CandidateValueDecisionError(
            f"{label} could not be read"
        ) from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != before.st_size:
        raise G1CV2CandidateValueDecisionError(
            f"{label} changed while being read"
        )
    return payload


def _write_once(destination: str | Path, value: dict[str, object]) -> None:
    try:
        path = Path(destination).expanduser().resolve()
    except (TypeError, ValueError) as error:
        raise G1CV2CandidateValueDecisionError(
            "candidate value decision destination path is invalid"
        ) from error
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "candidate value decision destination already exists"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise G1CV2CandidateValueDecisionError(
            "candidate value decision parent must be a real directory"
        )
    payload = _canonical_json(value).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        if path.exists() or path.is_symlink():
            raise FileExistsError(
                "candidate value decision destination appeared during write"
            )
        temporary.rename(path)
        path.chmod(0o600)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _decode_canonical_text(payload: str) -> dict[str, object]:
    if not isinstance(payload, str):
        raise G1CV2CandidateValueDecisionError(
            "candidate value decision must be text"
        )
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise G1CV2CandidateValueDecisionError(
            "candidate value decision must have one trailing newline"
        )
    try:
        document = json.loads(
            payload,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise G1CV2CandidateValueDecisionError(
            "candidate value decision is malformed JSON"
        ) from error
    if not isinstance(document, dict):
        raise G1CV2CandidateValueDecisionError(
            "candidate value decision must be one JSON object"
        )
    if _canonical_json(document) != payload:
        raise G1CV2CandidateValueDecisionError(
            "candidate value decision must use canonical JSON"
        )
    return document


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _canonical_json(value: object) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    return text


def _parse_positive_decimal(name: str, value: object) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise G1CV2CandidateValueDecisionError(
            f"{name} must be a positive finite decimal string"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise G1CV2CandidateValueDecisionError(
            f"{name} must be a positive finite decimal string"
        ) from error
    if not parsed.is_finite() or parsed <= 0:
        raise G1CV2CandidateValueDecisionError(
            f"{name} must be a positive finite decimal string"
        )
    if _decimal_text(parsed) != value:
        raise G1CV2CandidateValueDecisionError(
            f"{name} must use canonical decimal text"
        )
    return parsed


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise G1CV2CandidateValueDecisionError(
            f"{name} must be lowercase SHA-256 hex"
        )


def _require_non_empty_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise G1CV2CandidateValueDecisionError(
            f"{name} must be a non-empty string"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise G1CV2CandidateValueDecisionError(
            f"{name} must be a non-negative integer"
        )


def _require_decimals(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 255
    ):
        raise G1CV2CandidateValueDecisionError(
            f"{name} must be an integer within [0, 255]"
        )


def _require_positive_u64(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > _MAX_U64
    ):
        raise G1CV2CandidateValueDecisionError(
            f"{name} must be a positive u64 amount"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-candidate-value-decision",
        description=(
            "Write one explicit candidate-value decision from an "
            "authenticated MULTI_REFERENCE_REVIEW sizing proposal without "
            "granting candidate-authoring or runtime authority."
        ),
    )
    parser.add_argument("--sizing-proposal", required=True)
    parser.add_argument(
        "--decision",
        required=True,
        choices=sorted(_VALID_DECISIONS),
    )
    parser.add_argument("--decision-reason", required=True)
    parser.add_argument(
        "--replacement-entry-input-amount",
        type=int,
        default=None,
    )
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    try:
        result = decide_g1c_v2_candidate_value(
            sizing_proposal_path=args.sizing_proposal,
            decision=args.decision,
            decision_reason=args.decision_reason,
            replacement_entry_input_amount=(
                args.replacement_entry_input_amount
            ),
            destination=args.destination,
        )
    except (
        FileExistsError,
        G1CV2CandidateValueDecisionError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(
            _canonical_json({"status": "FAILED", "error": str(error)}),
            end="",
            file=sys.stderr,
        )
        return 1
    sys.stdout.write(_canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
