from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_cutover_authorization as authorization
import shreks_brain.fast_paper_runtime.authoritative_runtime as runtime


_SHA = "a" * 40
_MANIFEST_FP = "b" * 64
_CHAMPION_FP = "c" * 64
_BINDING_FP = "d" * 64
_POLICY_FP = "e" * 64


def _document() -> dict[str, object]:
    return authorization.build_fast_paper_cutover_authorization(
        release_source_sha=_SHA,
        manifest_fingerprint_sha256=_MANIFEST_FP,
        champion_version="champion-v1",
        champion_fingerprint_sha256=_CHAMPION_FP,
        action_policy_version=7,
        fast_run_id="fast-paper-run-1",
        binding_fingerprint_sha256=_BINDING_FP,
        execution_policy_fingerprint_sha256=_POLICY_FP,
        cutover_preflight_report_fingerprint_sha256="f" * 64,
        baseline_receipt_fingerprint_sha256="1" * 64,
        authorized_at_unix_ms=123_456,
    )


def _identity():
    manifest = SimpleNamespace(
        release_source_sha=_SHA,
        manifest_fingerprint_sha256=_MANIFEST_FP,
        champion_version="champion-v1",
        champion_fingerprint_sha256=_CHAMPION_FP,
        action_policy=SimpleNamespace(version=7),
    )
    binding = SimpleNamespace(
        fast_run_id="fast-paper-run-1",
        binding_fingerprint_sha256=_BINDING_FP,
    )
    policy = SimpleNamespace(policy_fingerprint_sha256=_POLICY_FP)
    return manifest, binding, policy


def test_cutover_authorization_round_trips_and_binds_runtime(
    tmp_path: Path,
) -> None:
    document = _document()
    path = tmp_path / "authorization.json"
    path.write_text(
        authorization.encode_fast_paper_cutover_authorization(document),
        encoding="utf-8",
    )

    restored = authorization.read_fast_paper_cutover_authorization(path)
    manifest, binding, policy = _identity()
    authorization.verify_fast_paper_cutover_authorization(
        restored,
        manifest=manifest,
        binding=binding,
        execution_policy=policy,
    )

    assert restored == document
    assert restored["production_paper_cutover"] == "GRANTED"
    assert restored["signing_submission_authority"] == "NOT_GRANTED"
    assert restored["live_authority"] == "DISABLED"


def test_cutover_authorization_rejects_identity_and_fingerprint_drift(
    tmp_path: Path,
) -> None:
    document = _document()
    manifest, binding, policy = _identity()
    with pytest.raises(
        authorization.FastPaperCutoverAuthorizationError,
        match="release_source_sha",
    ):
        authorization.verify_fast_paper_cutover_authorization(
            document,
            manifest=SimpleNamespace(
                **{
                    **manifest.__dict__,
                    "release_source_sha": "9" * 40,
                }
            ),
            binding=binding,
            execution_policy=policy,
        )

    path = tmp_path / "authorization.json"
    payload = authorization.encode_fast_paper_cutover_authorization(
        document
    ).replace(
        document["authorization_fingerprint_sha256"],
        "0" * 64,
    )
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(
        authorization.FastPaperCutoverAuthorizationError,
        match="fingerprint",
    ):
        authorization.read_fast_paper_cutover_authorization(path)


def test_runtime_preflight_does_not_require_cutover_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = SimpleNamespace(cutover_authorization_path=Path("/missing"))
    bootstrap = SimpleNamespace()
    monkeypatch.setattr(
        runtime,
        "load_fast_paper_authoritative_runtime_config",
        lambda: config,
    )
    monkeypatch.setattr(
        runtime,
        "bootstrap_fast_paper_authoritative_runtime",
        lambda _config: bootstrap,
    )
    monkeypatch.setattr(
        runtime,
        "_status_line",
        lambda *_args, **kwargs: kwargs["production_paper_cutover"],
    )
    monkeypatch.setattr(
        runtime,
        "read_fast_paper_cutover_authorization",
        lambda _path: pytest.fail(
            "preflight must not read production cutover authorization"
        ),
    )

    assert runtime.main(["--preflight"]) == 0


def test_runtime_normal_start_requires_and_propagates_cutover_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = SimpleNamespace(
        cutover_authorization_path=Path("/authorization.json")
    )
    manifest, binding, policy = _identity()
    bootstrap = SimpleNamespace(
        decision_bootstrap=SimpleNamespace(manifest=manifest),
        execution_bootstrap=SimpleNamespace(
            binding=binding,
            execution_policy=policy,
        ),
    )
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        runtime,
        "load_fast_paper_authoritative_runtime_config",
        lambda: config,
    )
    monkeypatch.setattr(
        runtime,
        "bootstrap_fast_paper_authoritative_runtime",
        lambda _config: bootstrap,
    )
    monkeypatch.setattr(
        runtime,
        "read_fast_paper_cutover_authorization",
        lambda path: (
            observed.setdefault("authorization_path", path) or _document()
        ),
    )
    monkeypatch.setattr(
        runtime,
        "verify_fast_paper_cutover_authorization",
        lambda document, **kwargs: observed.update(
            authorization=document,
            verify=kwargs,
        ),
    )
    monkeypatch.setattr(
        runtime,
        "_install_signal_handlers",
        lambda _event: {},
    )
    monkeypatch.setattr(
        runtime,
        "_restore_signal_handlers",
        lambda _previous: None,
    )
    monkeypatch.setattr(
        runtime,
        "run_fast_paper_authoritative_runtime",
        lambda supplied_config, **kwargs: observed.update(
            run_config=supplied_config,
            run=kwargs,
        ),
    )

    assert runtime.main([]) == 0
    assert observed["authorization_path"] == config.cutover_authorization_path
    assert observed["run_config"] is config
    assert observed["run"]["bootstrap"] is bootstrap
    assert (
        observed["run"]["production_paper_cutover"]
        == "GRANTED_AND_ACTIVE"
    )
