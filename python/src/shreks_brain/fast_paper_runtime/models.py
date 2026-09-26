from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shreks_brain.fast_campaign import FastCampaignContinuousActionPolicy
from shreks_brain.fast_paper import FAST_PAPER_EVENT_LOOP_VERSION


FAST_PAPER_RUNTIME_MANIFEST_SCHEMA_NAME = "shreks.fast_paper_runtime_manifest"
FAST_PAPER_RUNTIME_STATE_SCHEMA_NAME = "shreks.fast_paper_runtime_state"
FAST_PAPER_RUNTIME_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class FastPaperRuntimeManifest:
    schema_name: str
    schema_version: int
    release_source_sha: str
    runtime_mode: str
    champion_path: str
    champion_version: str
    champion_fingerprint_sha256: str
    champion_file_sha256: str
    decision_binary_path: str
    decision_binary_sha256: str
    feature_feed_binary_path: str
    feature_feed_binary_sha256: str
    action_policy: FastCampaignContinuousActionPolicy
    feature_schema_version: int
    state_version: str
    fast_paper_event_loop_version: str
    risk_policy_version: str
    fill_policy_version: str
    position_action_policy_version: str
    strategy_family: str
    strategy_version: str
    assessment_version: str
    observer_database_path: str
    paper_evidence_path: str
    checkpoint_path: str
    quote_provider: str
    quote_mint: str
    quote_decimals: int
    route_evidence_version: str
    manifest_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_RUNTIME_MANIFEST_SCHEMA_NAME:
            raise ValueError("Fast PAPER runtime manifest schema_name is incompatible")
        if self.schema_version != FAST_PAPER_RUNTIME_SCHEMA_VERSION:
            raise ValueError("Fast PAPER runtime manifest schema_version is incompatible")
        _require_source_sha("release_source_sha", self.release_source_sha)
        if self.runtime_mode != "PAPER":
            raise ValueError("Fast PAPER runtime manifest supports PAPER mode only")

        for name in (
            "champion_version",
            "state_version",
            "risk_policy_version",
            "fill_policy_version",
            "position_action_policy_version",
            "strategy_family",
            "strategy_version",
            "assessment_version",
            "quote_provider",
            "quote_mint",
            "route_evidence_version",
        ):
            _require_non_empty(name, getattr(self, name))

        for name in (
            "champion_path",
            "decision_binary_path",
            "feature_feed_binary_path",
            "observer_database_path",
            "paper_evidence_path",
            "checkpoint_path",
        ):
            _require_absolute_path(name, getattr(self, name))

        _require_sha256(
            "champion_fingerprint_sha256",
            self.champion_fingerprint_sha256,
        )
        _require_sha256("champion_file_sha256", self.champion_file_sha256)
        _require_sha256("decision_binary_sha256", self.decision_binary_sha256)
        _require_sha256(
            "feature_feed_binary_sha256",
            self.feature_feed_binary_sha256,
        )

        if type(self.action_policy) is not FastCampaignContinuousActionPolicy:
            raise ValueError(
                "action_policy must be an exact FastCampaignContinuousActionPolicy"
            )
        _require_positive_int("feature_schema_version", self.feature_schema_version)
        if self.fast_paper_event_loop_version != FAST_PAPER_EVENT_LOOP_VERSION:
            raise ValueError("Fast PAPER event-loop version is incompatible")
        if (
            isinstance(self.quote_decimals, bool)
            or not isinstance(self.quote_decimals, int)
            or not 0 <= self.quote_decimals <= 255
        ):
            raise ValueError("quote_decimals must be an integer within [0,255]")
        _require_sha256(
            "manifest_fingerprint_sha256",
            self.manifest_fingerprint_sha256,
        )


@dataclass(frozen=True, slots=True)
class FastPaperRuntimeCursor:
    decision_sequence: int
    decision_signature: str
    decision_ordinal: int
    decision_observed_at_unix_ms: int

    def __post_init__(self) -> None:
        _require_positive_int("decision_sequence", self.decision_sequence)
        _require_non_empty("decision_signature", self.decision_signature)
        _require_non_negative_int("decision_ordinal", self.decision_ordinal)
        _require_non_negative_int(
            "decision_observed_at_unix_ms",
            self.decision_observed_at_unix_ms,
        )


@dataclass(frozen=True, slots=True)
class FastPaperRuntimeState:
    schema_name: str
    schema_version: int
    manifest_fingerprint_sha256: str
    release_source_sha: str
    champion_fingerprint_sha256: str
    action_policy_version: int
    cursor: FastPaperRuntimeCursor | None
    state_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_RUNTIME_STATE_SCHEMA_NAME:
            raise ValueError("Fast PAPER runtime state schema_name is incompatible")
        if self.schema_version != FAST_PAPER_RUNTIME_SCHEMA_VERSION:
            raise ValueError("Fast PAPER runtime state schema_version is incompatible")
        _require_sha256(
            "manifest_fingerprint_sha256",
            self.manifest_fingerprint_sha256,
        )
        _require_source_sha("release_source_sha", self.release_source_sha)
        _require_sha256(
            "champion_fingerprint_sha256",
            self.champion_fingerprint_sha256,
        )
        _require_positive_int("action_policy_version", self.action_policy_version)
        if self.cursor is not None and type(self.cursor) is not FastPaperRuntimeCursor:
            raise ValueError("cursor must be an exact FastPaperRuntimeCursor or None")
        _require_sha256("state_fingerprint_sha256", self.state_fingerprint_sha256)


def _require_non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_source_sha(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a 40-character lowercase source SHA")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a 64-character lowercase SHA-256 digest")


def _require_absolute_path(name: str, value: object) -> None:
    _require_non_empty(name, value)
    assert isinstance(value, str)
    if not Path(value).is_absolute():
        raise ValueError(f"{name} must be an absolute path")
