from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json

from .codec import fingerprint_host_acceptance_record
from .models import HostAcceptanceRecord, HostAcceptanceStage, HostCheckStatus


HOST_CONTINUITY_SCHEMA_VERSION = "phase-g-host-continuity-v1"


class HostContinuityVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class HostContinuityFinding:
    code: str
    message: str

    def __post_init__(self) -> None:
        _require_text("code", self.code)
        _require_text("message", self.message)


@dataclass(frozen=True, slots=True)
class HostContinuityAssessment:
    schema_version: str
    verdict: HostContinuityVerdict
    before_fingerprint_sha256: str
    after_fingerprint_sha256: str
    findings: tuple[HostContinuityFinding, ...]

    def __post_init__(self) -> None:
        if self.schema_version != HOST_CONTINUITY_SCHEMA_VERSION:
            raise ValueError("unsupported host continuity schema version")
        if type(self.verdict) is not HostContinuityVerdict:
            raise ValueError("verdict must be an exact HostContinuityVerdict")
        _require_sha256("before_fingerprint_sha256", self.before_fingerprint_sha256)
        _require_sha256("after_fingerprint_sha256", self.after_fingerprint_sha256)
        if type(self.findings) is not tuple or any(
            type(item) is not HostContinuityFinding for item in self.findings
        ):
            raise ValueError("findings must contain exact HostContinuityFinding values")
        codes = tuple(item.code for item in self.findings)
        if len(codes) != len(set(codes)):
            raise ValueError("finding codes must be unique")
        expected = HostContinuityVerdict.PASS if not self.findings else HostContinuityVerdict.FAIL
        if self.verdict is not expected:
            raise ValueError("verdict must match findings")


def compare_host_acceptance_records(
    before: HostAcceptanceRecord,
    after: HostAcceptanceRecord,
) -> HostContinuityAssessment:
    if type(before) is not HostAcceptanceRecord or type(after) is not HostAcceptanceRecord:
        raise ValueError("before and after must be exact HostAcceptanceRecord values")

    findings: list[HostContinuityFinding] = []

    def add(code: str, message: str) -> None:
        if not any(item.code == code for item in findings):
            findings.append(HostContinuityFinding(code=code, message=message))

    if before.evidence_fingerprint_sha256 != fingerprint_host_acceptance_record(before):
        add("BEFORE_FINGERPRINT_INVALID", "baseline evidence fingerprint does not verify")
    if after.evidence_fingerprint_sha256 != fingerprint_host_acceptance_record(after):
        add("AFTER_FINGERPRINT_INVALID", "after evidence fingerprint does not verify")

    if before.overall_status is not HostCheckStatus.PASS:
        add("BEFORE_NOT_PASS", "baseline host acceptance record is not PASS")
    if after.overall_status is not HostCheckStatus.PASS:
        add("AFTER_NOT_PASS", "after host acceptance record is not PASS")

    allowed_after = {
        HostAcceptanceStage.AFTER_PROCESS_RESTART,
        HostAcceptanceStage.AFTER_REBOOT,
        HostAcceptanceStage.AFTER_RESTORE_DRILL,
    }
    if before.stage is not HostAcceptanceStage.BASELINE or after.stage not in allowed_after:
        add(
            "UNEXPECTED_STAGE_TRANSITION",
            "continuity comparison requires BASELINE followed by an after-drill stage",
        )

    if before.host_label_sha256 != after.host_label_sha256:
        add("HOST_CHANGED", "host identity hash changed across continuity records")

    before_release = (
        before.release.expected_source_sha,
        before.release.current_target_name,
        before.release.release_manifest_sha256,
    )
    after_release = (
        after.release.expected_source_sha,
        after.release.current_target_name,
        after.release.release_manifest_sha256,
    )
    if before_release != after_release:
        add("RELEASE_CHANGED", "active verified release changed across the continuity drill")

    if before.paper.paper_run_id != after.paper.paper_run_id:
        add("PAPER_RUN_CHANGED", "PAPER run identity changed across the continuity drill")
    if before.paper.candidate_version != after.paper.candidate_version:
        add("CANDIDATE_VERSION_CHANGED", "candidate version changed across the continuity drill")
    if (
        before.paper.campaign_manifest_fingerprint_sha256
        != after.paper.campaign_manifest_fingerprint_sha256
    ):
        add("CAMPAIGN_CHANGED", "campaign manifest fingerprint changed across the continuity drill")

    if after.paper.last_cycle_at_unix_ms < before.paper.last_cycle_at_unix_ms:
        add("PAPER_CYCLE_TIME_REGRESSED", "PAPER last-cycle timestamp moved backwards")
    if after.paper.ledger_as_of_unix_ms < before.paper.ledger_as_of_unix_ms:
        add("LEDGER_TIME_REGRESSED", "PAPER ledger timestamp moved backwards")
    if after.paper.ledger_entry_count < before.paper.ledger_entry_count:
        add("LEDGER_ENTRY_COUNT_REGRESSED", "PAPER ledger entry count decreased")
    if not set(before.paper.processed_intent_keys).issubset(after.paper.processed_intent_keys):
        add("PROCESSED_INTENT_LOST", "one or more previously processed intent keys disappeared")

    before_risk = (
        before.risk_control.schema_version,
        before.risk_control.revision,
        before.risk_control.halt_new_entries,
        before.risk_control.kill_switch_active,
        before.risk_control.state_file_sha256,
    )
    after_risk = (
        after.risk_control.schema_version,
        after.risk_control.revision,
        after.risk_control.halt_new_entries,
        after.risk_control.kill_switch_active,
        after.risk_control.state_file_sha256,
    )
    if before_risk != after_risk:
        add("RISK_CONTROL_CHANGED", "G7 operator risk-control state changed across the continuity drill")

    if before.stage is HostAcceptanceStage.BASELINE:
        if after.stage is HostAcceptanceStage.AFTER_PROCESS_RESTART:
            if before.resources.boot_id != after.resources.boot_id:
                add(
                    "PROCESS_RESTART_BOOT_ID_CHANGED",
                    "process restart evidence must remain within the same host boot",
                )
        elif after.stage is HostAcceptanceStage.AFTER_REBOOT:
            if before.resources.boot_id == after.resources.boot_id:
                add(
                    "REBOOT_BOOT_ID_UNCHANGED",
                    "reboot evidence requires a different host boot ID",
                )

    verdict = HostContinuityVerdict.PASS if not findings else HostContinuityVerdict.FAIL
    return HostContinuityAssessment(
        schema_version=HOST_CONTINUITY_SCHEMA_VERSION,
        verdict=verdict,
        before_fingerprint_sha256=before.evidence_fingerprint_sha256,
        after_fingerprint_sha256=after.evidence_fingerprint_sha256,
        findings=tuple(findings),
    )


def encode_host_continuity_assessment(assessment: HostContinuityAssessment) -> str:
    if type(assessment) is not HostContinuityAssessment:
        raise ValueError("assessment must be an exact HostContinuityAssessment")
    document = {
        "after_fingerprint_sha256": assessment.after_fingerprint_sha256,
        "before_fingerprint_sha256": assessment.before_fingerprint_sha256,
        "findings": [
            {"code": item.code, "message": item.message} for item in assessment.findings
        ],
        "schema_version": assessment.schema_version,
        "verdict": assessment.verdict.value,
    }
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def decode_host_continuity_assessment(payload: str | bytes) -> HostContinuityAssessment:
    if type(payload) is bytes:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("host continuity assessment must be UTF-8") from exc
    elif type(payload) is str:
        text = payload
    else:
        raise ValueError("host continuity assessment payload must be str or bytes")
    try:
        document = json.loads(
            text,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant: {value}")
            ),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid host continuity assessment JSON") from exc
    if type(document) is not dict:
        raise ValueError("host continuity assessment must be a JSON object")
    expected_keys = {
        "after_fingerprint_sha256",
        "before_fingerprint_sha256",
        "findings",
        "schema_version",
        "verdict",
    }
    if set(document) != expected_keys:
        raise ValueError("host continuity assessment keys must be exact")
    raw_findings = document["findings"]
    if type(raw_findings) is not list:
        raise ValueError("findings must be a JSON array")
    findings: list[HostContinuityFinding] = []
    for item in raw_findings:
        if type(item) is not dict or set(item) != {"code", "message"}:
            raise ValueError("finding keys must be exact")
        findings.append(HostContinuityFinding(code=item["code"], message=item["message"]))
    try:
        assessment = HostContinuityAssessment(
            schema_version=document["schema_version"],
            verdict=HostContinuityVerdict(document["verdict"]),
            before_fingerprint_sha256=document["before_fingerprint_sha256"],
            after_fingerprint_sha256=document["after_fingerprint_sha256"],
            findings=tuple(findings),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid host continuity assessment fields") from exc
    if encode_host_continuity_assessment(assessment) != text:
        raise ValueError("host continuity assessment JSON is not canonical")
    return assessment


def _require_text(name: str, value: object) -> None:
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError(f"{name} must be non-empty trimmed text")


def _require_sha256(name: str, value: object) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
