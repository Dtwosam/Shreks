from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_candidate_attribution as attribution
import shreks_brain.fast_paper_runtime.shadow_service as service
from shreks_brain.fast_paper_runtime import (
    FastPaperShadowCandidateAttributionRequest,
    resolve_fast_paper_shadow_candidate_id,
)

from test_fast_paper_shadow_decision import _manifest
from test_fast_paper_shadow_service import _config, _policy_document


def _database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE token_candidates (
                id INTEGER PRIMARY KEY,
                mint TEXT NOT NULL
            );
            CREATE TABLE paper_quote_snapshots (
                candidate_id INTEGER NOT NULL,
                purpose TEXT NOT NULL,
                provider TEXT NOT NULL,
                probe_policy_version TEXT NOT NULL,
                input_mint TEXT NOT NULL,
                output_mint TEXT NOT NULL,
                taker TEXT NOT NULL,
                input_amount TEXT NOT NULL,
                slippage_bps INTEGER NOT NULL,
                quoted_at_unix_ms INTEGER NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO token_candidates(id, mint) VALUES (?, ?)",
            ((11, "Mint111"), (17, "Mint111")),
        )
        connection.executemany(
            """
            INSERT INTO paper_quote_snapshots(
                candidate_id,
                purpose,
                provider,
                probe_policy_version,
                input_mint,
                output_mint,
                taker,
                input_amount,
                slippage_bps,
                quoted_at_unix_ms
            ) VALUES (?, 'entry', 'jupiter', 'probe-v1', ?,
                      'Mint111', 'Taker111', ?, 75, ?)
            """,
            (
                (11, "WrongQuote", "100000", 1_025),
                (
                    17,
                    "So11111111111111111111111111111111111111112",
                    "100000",
                    1_025,
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _request(manifest):
    return FastPaperShadowCandidateAttributionRequest(
        mint="Mint111",
        quote_mint=manifest.quote_mint,
        decision_observed_at_unix_ms=1_000,
        evaluated_at_unix_ms=1_050,
        probe_policy_version="probe-v1",
        taker="Taker111",
        slippage_bps=75,
        entry_input_amount_raw=100_000,
        max_quote_age_ms=100,
    )


def test_candidate_attribution_resolves_exact_persisted_entry_probe(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    _database(Path(manifest.observer_database_path))

    assert (
        resolve_fast_paper_shadow_candidate_id(
            manifest,
            _request(manifest),
        )
        == 17
    )


def test_candidate_attribution_rejects_manifest_quote_mint_drift(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    _database(Path(manifest.observer_database_path))
    request = FastPaperShadowCandidateAttributionRequest(
        mint="Mint111",
        quote_mint="WrongQuote",
        decision_observed_at_unix_ms=1_000,
        evaluated_at_unix_ms=1_050,
        probe_policy_version="probe-v1",
        taker="Taker111",
        slippage_bps=75,
        entry_input_amount_raw=100_000,
        max_quote_age_ms=100,
    )

    with pytest.raises(ValueError, match="quote mint|manifest"):
        resolve_fast_paper_shadow_candidate_id(
            manifest,
            request,
        )


def test_candidate_attribution_fails_closed_when_exact_identity_is_ambiguous(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    database = Path(manifest.observer_database_path)
    _database(database)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            INSERT INTO paper_quote_snapshots(
                candidate_id,
                purpose,
                provider,
                probe_policy_version,
                input_mint,
                output_mint,
                taker,
                input_amount,
                slippage_bps,
                quoted_at_unix_ms
            ) VALUES (11, 'entry', 'jupiter', 'probe-v1', ?,
                      'Mint111', 'Taker111', '100000', 75, 1030)
            """,
            (manifest.quote_mint,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="missing or ambiguous"):
        resolve_fast_paper_shadow_candidate_id(
            manifest,
            _request(manifest),
        )


def test_candidate_attribution_rejects_quote_outside_decision_window(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    database = Path(manifest.observer_database_path)
    _database(database)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE paper_quote_snapshots SET quoted_at_unix_ms = 999 WHERE candidate_id = 17"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="missing or ambiguous"):
        resolve_fast_paper_shadow_candidate_id(
            manifest,
            _request(manifest),
        )


def test_shadow_service_delegates_candidate_attribution_to_public_resolver(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    policy = service.FastPaperShadowServicePolicy(**_policy_document())
    manifest = SimpleNamespace(
        observer_database_path=str(tmp_path / "observer.sqlite3"),
        quote_provider="jupiter",
        quote_mint="Quote111",
    )
    state = object()
    next_state = object()
    record = SimpleNamespace(
        decision_observed_at_unix_ms=1_000,
        mint="Mint111",
        quote_mint="Quote111",
    )
    bootstrap = service.FastPaperShadowServiceBootstrap(
        manifest=manifest,
        policy=policy,
        state=state,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        service,
        "_validate_service_paths",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        service,
        "fetch_fast_paper_runtime_feature_batch",
        lambda *_args, **_kwargs: SimpleNamespace(
            records=(record,),
            next_state=next_state,
        ),
    )
    monkeypatch.setattr(
        service,
        "_resolve_candidate_id",
        lambda *_args, **_kwargs: pytest.fail(
            "service must not retain private candidate attribution"
        ),
        raising=False,
    )

    def resolve_candidate(supplied_manifest, request):
        captured["manifest"] = supplied_manifest
        captured["request"] = request
        return 17

    monkeypatch.setattr(
        service,
        "resolve_fast_paper_shadow_candidate_id",
        resolve_candidate,
        raising=False,
    )
    monkeypatch.setattr(
        service,
        "resolve_fast_paper_shadow_cycle_input",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        service,
        "run_fast_paper_shadow_batch",
        lambda *_args, **_kwargs: next_state,
    )

    updated, processed = service.run_fast_paper_shadow_service_cycle(
        bootstrap,
        config,
        clock_unix_ms=lambda: 1_050,
    )

    assert processed == 1
    assert updated.state is next_state
    request = captured["request"]
    assert type(request) is FastPaperShadowCandidateAttributionRequest
    assert request.mint == "Mint111"
    assert request.quote_mint == "Quote111"
    assert request.decision_observed_at_unix_ms == 1_000
    assert request.evaluated_at_unix_ms == 1_050
    assert request.probe_policy_version == "probe-v1"
    assert request.taker == "Taker111"
    assert request.slippage_bps == 75
    assert request.entry_input_amount_raw == 100_000
    assert request.max_quote_age_ms == 5_000


def test_candidate_attribution_source_is_query_only_and_has_no_execution_authority() -> None:
    payload = Path(attribution.__file__).read_text(encoding="utf-8")
    for required in (
        "mode=ro",
        "PRAGMA query_only = ON",
        "paper_quote_snapshots",
        "token_candidates",
    ):
        assert required in payload

    for forbidden in (
        "FastPaperShadowQuoteUsdEvidence(",
        "ObserverMarketStore",
        "produce_fast_paper_shadow_execution_input_source_record",
        "execute_fast_paper_shadow_decision(",
        "commit_fast_paper_shadow_transition_atomically",
        "requests",
        "httpx",
        "urllib",
        "RuntimeMode.LIVE",
        "shreks_brain.scoring",
        "score_candidate",
    ):
        assert forbidden not in payload
