from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import os

import pytest

import shreks_brain.fast_paper_authoritative_host_prepare as host


_SHA = "a" * 40


def test_provision_roots_creates_exact_service_owned_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "fast-paper-authoritative"
    decision = root / "decision"
    execution = root / "execution-sources"
    buy = root / "buy-authority-sources"
    usd = root / "quote-usd-sources"
    reduction = root / "reduction-sources"
    retry = root / "pending-buy-retry-sources"
    config = SimpleNamespace(
        decision_config=SimpleNamespace(evidence_directory=decision),
        execution_config=SimpleNamespace(source_directory=execution),
        buy_authority_source_directory=buy,
        quote_usd_source_directory=usd,
        reduction_source_directory=reduction,
        pending_buy_retry_source_directory=retry,
    )
    manifest = SimpleNamespace(manifest_fingerprint_sha256="1" * 64)
    monkeypatch.setattr(host, "_require_root", lambda: None)
    monkeypatch.setattr(
        host,
        "_require_release_runtime",
        lambda *_args, **_kwargs: tmp_path / _SHA,
    )
    monkeypatch.setattr(
        host,
        "_read_installed_config",
        lambda *_args, **_kwargs: (
            {"A": "B"},
            config,
            manifest,
        ),
    )
    monkeypatch.setattr(
        host,
        "encode_fast_paper_authoritative_cutover_environment",
        lambda _env: "A=B\n",
    )
    monkeypatch.setattr(host.os, "chown", lambda *_args: None)

    receipt = host.provision_fast_paper_authoritative_host_roots(
        expected_release_source_sha=_SHA,
        current_link=tmp_path / "current",
        config_destination=tmp_path / "env",
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
    )

    assert receipt["state"] == "ROOTS_CREATED"
    for path in (root, decision, execution, buy, usd, reduction, retry):
        assert path.is_dir()
        assert path.stat().st_mode & 0o777 == 0o700

    replay = host.provision_fast_paper_authoritative_host_roots(
        expected_release_source_sha=_SHA,
        current_link=tmp_path / "current",
        config_destination=tmp_path / "env",
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
    )
    assert replay["state"] == "ROOTS_VERIFIED"


def test_baseline_authentication_rejects_decision_state_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shadow = tmp_path / "shadow.json"
    authoritative = tmp_path / "authoritative.json"
    shadow.write_bytes(b"same\n")
    authoritative.write_bytes(b"same\n")
    manifest = SimpleNamespace(
        release_source_sha=_SHA,
        manifest_fingerprint_sha256="2" * 64,
    )
    monkeypatch.setattr(
        host,
        "read_fast_paper_authoritative_cutover_baseline_receipt",
        lambda _path: {
            "release_source_sha": _SHA,
            "manifest_fingerprint_sha256": "2" * 64,
            "authoritative_checkpoint_path": str(authoritative.resolve()),
            "decision_state_fingerprint_sha256": "3" * 64,
            "decision_cursor_sequence": None,
            "shadow_checkpoint_path": str(shadow.resolve()),
            "shadow_checkpoint_file_sha256": __import__("hashlib").sha256(
                shadow.read_bytes()
            ).hexdigest(),
            "receipt_fingerprint_sha256": "4" * 64,
        },
    )
    monkeypatch.setattr(
        host,
        "read_fast_paper_runtime_state",
        lambda _path: SimpleNamespace(
            state_fingerprint_sha256="9" * 64,
            cursor=None,
        ),
    )

    with pytest.raises(
        host.FastPaperAuthoritativeHostPrepareError,
        match="identity mismatch",
    ):
        host._authenticate_baseline_receipt(
            tmp_path / "receipt.json",
            manifest=manifest,
            decision_checkpoint_path=authoritative,
        )


def test_host_preflight_authenticates_writer_policy_and_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dirs = tuple(tmp_path / name for name in (
        "decision",
        "execution",
        "buy",
        "usd",
        "reduction",
        "retry",
    ))
    for path in dirs:
        path.mkdir()
    checkpoint = dirs[0] / "runtime-state.json"
    checkpoint.write_text("{}\n", encoding="utf-8")
    config = SimpleNamespace(
        decision_config=SimpleNamespace(
            evidence_directory=dirs[0],
            checkpoint_path=checkpoint,
            policy_path=tmp_path / "service-policy.json",
        ),
        execution_config=SimpleNamespace(source_directory=dirs[1]),
        buy_authority_source_directory=dirs[2],
        quote_usd_source_directory=dirs[3],
        reduction_source_directory=dirs[4],
        pending_buy_retry_source_directory=dirs[5],
        buy_writer_policy_path=tmp_path / "buy-policy.json",
    )
    manifest = SimpleNamespace(
        manifest_fingerprint_sha256="1" * 64,
        release_source_sha=_SHA,
    )
    writer = SimpleNamespace(policy_fingerprint_sha256="5" * 64)
    monkeypatch.setattr(host, "_require_root", lambda: None)
    monkeypatch.setattr(
        host,
        "_require_release_runtime",
        lambda *_args, **_kwargs: tmp_path / _SHA,
    )
    monkeypatch.setattr(
        host,
        "_read_installed_config",
        lambda *_args, **_kwargs: ({"A": "B"}, config, manifest),
    )
    monkeypatch.setattr(
        host,
        "_require_path_metadata",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        host,
        "_authenticate_baseline_receipt",
        lambda *_args, **_kwargs: {
            "decision_state_fingerprint_sha256": "6" * 64,
            "receipt_fingerprint_sha256": "7" * 64,
        },
    )
    monkeypatch.setattr(
        host,
        "read_fast_paper_shadow_service_policy",
        lambda _path: SimpleNamespace(),
    )
    monkeypatch.setattr(
        host,
        "read_fast_paper_shadow_buy_writer_policy",
        lambda _path: writer,
    )
    observed = []
    monkeypatch.setattr(
        host,
        "verify_fast_paper_shadow_buy_writer_policy_bindings",
        lambda *_args: observed.append("verified"),
    )
    monkeypatch.setattr(
        host,
        "bootstrap_fast_paper_authoritative_runtime",
        lambda _config: SimpleNamespace(
            execution_bootstrap=SimpleNamespace(
                runtime_state=SimpleNamespace(market_positions=()),
                checkpoint=SimpleNamespace(
                    sequence=0,
                    state=SimpleNamespace(pending_buy=None),
                ),
                binding=SimpleNamespace(fast_run_id="fast-run-1"),
            )
        ),
    )
    monkeypatch.setattr(
        host,
        "encode_fast_paper_authoritative_cutover_environment",
        lambda _env: "A=B\n",
    )

    receipt = host.preflight_fast_paper_authoritative_host(
        expected_release_source_sha=_SHA,
        current_link=tmp_path / "current",
        config_destination=tmp_path / "env",
        baseline_receipt_path=tmp_path / "receipt",
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
    )

    assert receipt["state"] == "READY_FOR_PROTECTED_PAPER_CUTOVER_REVIEW"
    assert receipt["paper_checkpoint_sequence"] == 0
    assert receipt["fast_run_id"] == "fast-run-1"
    assert observed == ["verified"]


def test_authoritative_host_prepare_has_no_service_control_or_trade_authority() -> None:
    source = Path(host.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "systemctl",
        "subprocess",
        "run_fast_paper_authoritative_execution",
        "commit_fast_paper_authoritative_transition_atomically",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
    assert '"production_paper_cutover": "NOT_GRANTED"' in source
    assert '"service_control_authority": "NOT_GRANTED"' in source
