from __future__ import annotations

import json
from pathlib import Path
import stat

import pytest

from shreks_brain.g1c_v2_quote_valuation_reference import (
    G1CV2QuoteValuationReferenceError,
    capture_g1c_v2_quote_valuation_reference,
    decode_g1c_v2_quote_valuation_reference,
)

from test_observer_quote_asset_usd_evidence import (
    AS_OF,
    TOKEN,
    WSOL,
    _database,
    _snapshot,
)


def test_reference_captures_exact_market_quote_usd_rate_read_only(
    tmp_path: Path,
) -> None:
    database = tmp_path / "observer.sqlite3"
    candidate_id = _database(database)
    row_id = _snapshot(database, candidate_id)
    before = database.stat()
    destination = tmp_path / "reference.json"

    reference = capture_g1c_v2_quote_valuation_reference(
        database_path=database,
        candidate_id=candidate_id,
        as_of_unix_ms=AS_OF,
        source="dexscreener",
        venue="pump_swap",
        base_mint=TOKEN,
        quote_mint=WSOL,
        max_age_ms=60_000,
        expected_market_row_id=row_id,
        destination=destination,
    )

    after = database.stat()
    assert reference["schema_name"] == "shreks.g1c_v2_quote_valuation_reference"
    assert reference["schema_version"] == 1
    assert reference["status"] == "REFERENCE_EVIDENCE_ONLY"
    assert reference["valuation_mode"] == "exact_market_ratio"
    assert reference["market_row_id"] == row_id
    assert reference["candidate_id"] == candidate_id
    assert reference["observed_at_unix_ms"] == AS_OF - 1_000
    assert reference["as_of_unix_ms"] == AS_OF
    assert reference["max_age_ms"] == 60_000
    assert reference["source"] == "dexscreener"
    assert reference["venue"] == "pump_swap"
    assert reference["pair_address"] == "Pair111"
    assert reference["base_mint"] == TOKEN
    assert reference["quote_mint"] == WSOL
    assert reference["base_price_quote"] == "0.002"
    assert reference["base_price_usd"] == "0.33"
    assert reference["quote_asset_usd_per_token"] == "165"
    assert reference["candidate_value_authority"] == "NOT_GRANTED"
    assert reference["candidate_authoring_authority"] == "NOT_GRANTED"
    assert reference["rotation_authority"] == "NOT_GRANTED"
    assert reference["scoring_authority"] == "NOT_GRANTED"
    assert reference["paper_promotion_authority"] == "BLOCKED"
    assert reference["live_authority"] == "DISABLED"
    assert len(reference["reference_fingerprint_sha256"]) == 64

    assert before.st_size == after.st_size
    assert before.st_mtime_ns == after.st_mtime_ns
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert decode_g1c_v2_quote_valuation_reference(
        destination.read_text(encoding="utf-8")
    ) == reference


def test_reference_selection_is_deterministic_without_expected_row(
    tmp_path: Path,
) -> None:
    database = tmp_path / "observer.sqlite3"
    candidate_id = _database(database)
    older = _snapshot(
        database,
        candidate_id,
        observed_at_unix_ms=AS_OF - 1_000,
        price_native="0.002",
        price_usd=0.33,
    )
    current = _snapshot(
        database,
        candidate_id,
        observed_at_unix_ms=AS_OF - 500,
        price_native="0.002",
        price_usd=0.36,
    )
    assert current != older

    reference = capture_g1c_v2_quote_valuation_reference(
        database_path=database,
        candidate_id=candidate_id,
        as_of_unix_ms=AS_OF,
        source="dexscreener",
        venue="pump_swap",
        base_mint=TOKEN,
        quote_mint=WSOL,
        max_age_ms=60_000,
        expected_market_row_id=None,
        destination=tmp_path / "reference.json",
    )

    assert reference["market_row_id"] == current
    assert reference["observed_at_unix_ms"] == AS_OF - 500
    assert reference["quote_asset_usd_per_token"] == "180"


def test_reference_rejects_wrong_expected_row_without_output(
    tmp_path: Path,
) -> None:
    database = tmp_path / "observer.sqlite3"
    candidate_id = _database(database)
    older = _snapshot(database, candidate_id, observed_at_unix_ms=AS_OF - 1_000)
    _snapshot(database, candidate_id, observed_at_unix_ms=AS_OF - 500)
    destination = tmp_path / "reference.json"

    with pytest.raises(G1CV2QuoteValuationReferenceError, match="row|market"):
        capture_g1c_v2_quote_valuation_reference(
            database_path=database,
            candidate_id=candidate_id,
            as_of_unix_ms=AS_OF,
            source="dexscreener",
            venue="pump_swap",
            base_mint=TOKEN,
            quote_mint=WSOL,
            max_age_ms=60_000,
            expected_market_row_id=older,
            destination=destination,
        )

    assert not destination.exists()


def test_reference_rejects_stale_or_wrong_identity_evidence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "observer.sqlite3"
    candidate_id = _database(database)
    _snapshot(database, candidate_id, observed_at_unix_ms=AS_OF - 100_000)

    with pytest.raises(G1CV2QuoteValuationReferenceError, match="fresh|market"):
        capture_g1c_v2_quote_valuation_reference(
            database_path=database,
            candidate_id=candidate_id,
            as_of_unix_ms=AS_OF,
            source="dexscreener",
            venue="pump_swap",
            base_mint=TOKEN,
            quote_mint=WSOL,
            max_age_ms=1_000,
            expected_market_row_id=None,
            destination=tmp_path / "stale.json",
        )

    with pytest.raises(G1CV2QuoteValuationReferenceError, match="fresh|market"):
        capture_g1c_v2_quote_valuation_reference(
            database_path=database,
            candidate_id=candidate_id,
            as_of_unix_ms=AS_OF,
            source="dexscreener",
            venue="raydium",
            base_mint=TOKEN,
            quote_mint=WSOL,
            max_age_ms=200_000,
            expected_market_row_id=None,
            destination=tmp_path / "wrong.json",
        )


def test_reference_is_write_once_and_decoder_rejects_authority_escalation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "observer.sqlite3"
    candidate_id = _database(database)
    _snapshot(database, candidate_id)
    destination = tmp_path / "reference.json"
    kwargs = dict(
        database_path=database,
        candidate_id=candidate_id,
        as_of_unix_ms=AS_OF,
        source="dexscreener",
        venue="pump_swap",
        base_mint=TOKEN,
        quote_mint=WSOL,
        max_age_ms=60_000,
        expected_market_row_id=None,
        destination=destination,
    )
    reference = capture_g1c_v2_quote_valuation_reference(**kwargs)

    with pytest.raises(FileExistsError):
        capture_g1c_v2_quote_valuation_reference(**kwargs)

    tampered = dict(reference)
    tampered["candidate_value_authority"] = "GRANTED"
    payload = (
        json.dumps(
            tampered,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )
    with pytest.raises(G1CV2QuoteValuationReferenceError, match="authority|fingerprint"):
        decode_g1c_v2_quote_valuation_reference(payload)


def test_reference_cli_is_registered_and_bounded_to_read_only_market_evidence() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "shreks_brain" / "g1c_v2_quote_valuation_reference.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-quote-valuation-reference = '
        '"shreks_brain.g1c_v2_quote_valuation_reference:main"'
        in pyproject
    )
    assert "ObserverMarketStore" in source
    assert "quote_asset_usd_evidence" in source
    for forbidden in (
        "/etc/shreks",
        "/opt/shreks",
        "/var/lib/shreks",
        "systemctl",
        "subprocess",
        "author_g1c_v2_runtime_manifest_candidate",
        "bind_g1c_v2_runtime_manifest_candidate_authority",
        "bind_g1c_v2_runtime_manifest_transition",
        "rotate_paper_manifest",
        "score_candidate",
        "model_fit",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
