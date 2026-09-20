from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

import shreks_brain.fl9_v2_runtime_manifest_discovery as discovery
from shreks_brain.observer_campaign.runtime_manifest import (
    encode_observer_paper_campaign_runtime_manifest,
)

from test_fl9_v2_runtime_manifest_discovery import (
    QUOTE,
    _bind_synthetic_cohort_to_request_authority,
    _compatible_manifest,
    _prior_request_authority,
)
from test_fl9_v2_cohort_acceptance_artifact import _write as _write_cohort
from test_observer_campaign_runtime_manifest import _manifest


def _module():
    return importlib.import_module(
        "shreks_brain.fl9_v2_runtime_manifest_candidate_assessment"
    )


def _inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    manifest,
) -> tuple[Path, Path, Path]:
    cohort = _write_cohort(tmp_path, "cohort")
    request_path, _policy_path, request, _policy = _prior_request_authority(
        tmp_path,
        cohort.path,
    )
    _bind_synthetic_cohort_to_request_authority(
        monkeypatch,
        cohort,
        request,
    )
    candidate = tmp_path / "candidate-paper-campaign.json"
    candidate.write_bytes(
        encode_observer_paper_campaign_runtime_manifest(manifest)
    )
    return cohort.path, request_path, candidate


def test_candidate_assessment_accepts_compatible_authenticated_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    cohort, request, candidate = _inputs(
        tmp_path,
        monkeypatch,
        manifest=_compatible_manifest(),
    )

    report = module.assess_fl9_v2_runtime_manifest_candidate(
        cohort_path=cohort,
        runtime_manifest_path=candidate,
        v2_host_request_authority_path=request,
    )

    assert report["schema_name"] == (
        "shreks.fl9_v2_runtime_manifest_candidate_assessment"
    )
    assert report["schema_version"] == 1
    assert report["status"] == "COMPATIBLE"
    assert report["cohort_quote_mint"] == QUOTE
    assert report["candidate"]["authentication"] == "AUTHENTICATED"
    assert report["candidate"]["compatibility"] == "COMPATIBLE"
    assert report["candidate"]["source_kind"] == "candidate"
    assert report["candidate"]["source_path"] == str(candidate.resolve())
    assert report["candidate"]["quote_asset_mint"] == QUOTE
    assert report["candidate"]["regime_quote_asset_mint"] == QUOTE
    assert report["candidate"]["safety_probe_output_mint"] == QUOTE

    authority = report["non_manifest_input_authority"]
    assert authority["authority_kind"] == "v2_host_request"
    assert authority["request_path"] == str(request.resolve())


def test_candidate_assessment_truthfully_reports_quote_policy_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    cohort, request, candidate = _inputs(
        tmp_path,
        monkeypatch,
        manifest=_manifest(),
    )
    before = candidate.read_bytes()

    report = module.assess_fl9_v2_runtime_manifest_candidate(
        cohort_path=cohort,
        runtime_manifest_path=candidate,
        v2_host_request_authority_path=request,
    )

    assert report["status"] == "REJECTED_QUOTE_POLICY"
    assert report["candidate"]["compatibility"] == "REJECTED_QUOTE_POLICY"
    assert candidate.read_bytes() == before


def test_candidate_assessment_fails_closed_on_tampered_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    cohort, request, candidate = _inputs(
        tmp_path,
        monkeypatch,
        manifest=_compatible_manifest(),
    )
    document = json.loads(candidate.read_text(encoding="utf-8"))
    document["paper_run_id"] = "tampered-run"
    candidate.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(
        module.RuntimeManifestCandidateAssessmentError,
        match="manifest|authenticate|fingerprint",
    ):
        module.assess_fl9_v2_runtime_manifest_candidate(
            cohort_path=cohort,
            runtime_manifest_path=candidate,
            v2_host_request_authority_path=request,
        )


def test_candidate_assessment_cli_is_registered_and_read_only() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "src"
        / "shreks_brain"
        / "fl9_v2_runtime_manifest_candidate_assessment.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-fl9-v2-runtime-manifest-candidate-assessment = '
        '"shreks_brain.fl9_v2_runtime_manifest_candidate_assessment:main"'
        in pyproject
    )

    for forbidden in (
        "write_bytes(",
        "write_text(",
        "open(\"w",
        "open('w",
        "sqlite3",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "registry promotion",
        "systemctl",
        "sudo ",
    ):
        assert forbidden not in source
