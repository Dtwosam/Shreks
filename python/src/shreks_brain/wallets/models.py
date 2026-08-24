from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math


class WalletActionKind(StrEnum):
    BUY = "buy"
    SELL = "sell"
    TRANSFER = "transfer"
    LIQUIDITY_EVENT = "liquidity_event"
    CREATOR_ACTION = "creator_action"
    OTHER = "other"


class WalletObservationEvidence(StrEnum):
    DIRECT = "direct"
    INFERRED = "inferred"


class WalletTradeEpisodeState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNRESOLVED = "UNRESOLVED"


class WalletTradeEvidenceQuality(StrEnum):
    DIRECT = "DIRECT"
    MIXED = "MIXED"
    INFERRED = "INFERRED"


class WalletTradeFindingCode(StrEnum):
    BUY_ECONOMICS_INCOMPLETE = "BUY_ECONOMICS_INCOMPLETE"
    SELL_ECONOMICS_INCOMPLETE = "SELL_ECONOMICS_INCOMPLETE"
    BUY_DELTA_DIRECTION_INVALID = "BUY_DELTA_DIRECTION_INVALID"
    SELL_DELTA_DIRECTION_INVALID = "SELL_DELTA_DIRECTION_INVALID"
    SELL_WITHOUT_KNOWN_ENTRY = "SELL_WITHOUT_KNOWN_ENTRY"
    SELL_EXCEEDS_KNOWN_INVENTORY = "SELL_EXCEEDS_KNOWN_INVENTORY"
    COUNTER_ASSET_CHANGED = "COUNTER_ASSET_CHANGED"
    NON_TRADE_INVENTORY_CHANGE = "NON_TRADE_INVENTORY_CHANGE"
    OPEN_POSITION = "OPEN_POSITION"


@dataclass(frozen=True, slots=True)
class WalletObservation:
    provider: str
    wallet: str
    candidate_mint: str
    action: WalletActionKind
    evidence: WalletObservationEvidence
    signature: str
    event_index: int
    slot: int
    observed_at_unix_ms: int
    occurred_at_unix_ms: int | None
    candidate_token_delta_raw: int | None
    counter_asset_mint: str | None
    counter_asset_delta_raw: int | None
    venue: str | None
    counterparty: str | None

    def __post_init__(self) -> None:
        _require_non_empty_string("provider", self.provider)
        _require_non_empty_string("wallet", self.wallet)
        _require_non_empty_string("candidate_mint", self.candidate_mint)
        if not isinstance(self.action, WalletActionKind):
            raise ValueError("action must be a WalletActionKind")
        if not isinstance(self.evidence, WalletObservationEvidence):
            raise ValueError("evidence must be a WalletObservationEvidence")
        _require_non_empty_string("signature", self.signature)
        _require_non_negative_int("event_index", self.event_index)
        _require_non_negative_int("slot", self.slot)
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        _require_optional_non_negative_int("occurred_at_unix_ms", self.occurred_at_unix_ms)
        _require_optional_int("candidate_token_delta_raw", self.candidate_token_delta_raw)
        _require_optional_non_empty_string("counter_asset_mint", self.counter_asset_mint)
        _require_optional_int("counter_asset_delta_raw", self.counter_asset_delta_raw)
        if self.counter_asset_delta_raw is not None and self.counter_asset_mint is None:
            raise ValueError("counter_asset_delta_raw requires counter_asset_mint")
        _require_optional_non_empty_string("venue", self.venue)
        _require_optional_non_empty_string("counterparty", self.counterparty)


@dataclass(frozen=True, slots=True)
class WalletTradeFinding:
    code: WalletTradeFindingCode
    message: str
    observed_at_unix_ms: int | None = None
    signature: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, WalletTradeFindingCode):
            raise ValueError("code must be a WalletTradeFindingCode")
        _require_non_empty_string("message", self.message)
        _require_optional_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        _require_optional_non_empty_string("signature", self.signature)


@dataclass(frozen=True, slots=True)
class WalletTradeEpisode:
    wallet: str
    candidate_mint: str
    episode_index: int
    state: WalletTradeEpisodeState
    evidence_quality: WalletTradeEvidenceQuality
    opened_at_unix_ms: int
    last_observed_at_unix_ms: int
    closed_at_unix_ms: int | None
    counter_asset_mint: str | None
    total_bought_quantity_raw: int
    total_sold_quantity_raw: int
    remaining_quantity_raw: int
    total_entry_cost_counter_raw: int
    total_exit_proceeds_counter_raw: int
    estimated_realized_pnl_counter_raw: int | None
    estimated_return_pct: float | None
    trade_observation_ids: tuple[str, ...]
    findings: tuple[WalletTradeFinding, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("wallet", self.wallet)
        _require_non_empty_string("candidate_mint", self.candidate_mint)
        _require_non_negative_int("episode_index", self.episode_index)
        if not isinstance(self.state, WalletTradeEpisodeState):
            raise ValueError("state must be a WalletTradeEpisodeState")
        if not isinstance(self.evidence_quality, WalletTradeEvidenceQuality):
            raise ValueError("evidence_quality must be a WalletTradeEvidenceQuality")
        _require_non_negative_int("opened_at_unix_ms", self.opened_at_unix_ms)
        _require_non_negative_int("last_observed_at_unix_ms", self.last_observed_at_unix_ms)
        if self.last_observed_at_unix_ms < self.opened_at_unix_ms:
            raise ValueError("last_observed_at_unix_ms must not precede opened_at_unix_ms")
        _require_optional_non_negative_int("closed_at_unix_ms", self.closed_at_unix_ms)
        if self.closed_at_unix_ms is not None:
            if not self.opened_at_unix_ms <= self.closed_at_unix_ms <= self.last_observed_at_unix_ms:
                raise ValueError("closed_at_unix_ms must be within the episode chronology")
        _require_optional_non_empty_string("counter_asset_mint", self.counter_asset_mint)
        for name, value in (
            ("total_bought_quantity_raw", self.total_bought_quantity_raw),
            ("total_sold_quantity_raw", self.total_sold_quantity_raw),
            ("remaining_quantity_raw", self.remaining_quantity_raw),
            ("total_entry_cost_counter_raw", self.total_entry_cost_counter_raw),
            ("total_exit_proceeds_counter_raw", self.total_exit_proceeds_counter_raw),
        ):
            _require_non_negative_int(name, value)
        if self.state is not WalletTradeEpisodeState.UNRESOLVED:
            if self.remaining_quantity_raw != self.total_bought_quantity_raw - self.total_sold_quantity_raw :
                raise ValueError("remaining_quantity_raw must reconcile bought and sold quantities")
        _require_optional_int("estimated_realized_pnl_counter_raw", self.estimated_realized_pnl_counter_raw)
        if self.estimated_return_pct is not None:
            if isinstance(self.estimated_return_pct, bool) or not isinstance(self.estimated_return_pct, (int, float)) or not math.isfinite(float(self.estimated_return_pct)):
                raise ValueError("estimated_return_pct must be finite when present")
        if not isinstance(self.trade_observation_ids, tuple) or not self.trade_observation_ids:
            raise ValueError("trade_observation_ids must be a non-empty tuple")
        if not all(isinstance(value, str) and value.strip() for value in self.trade_observation_ids):
            raise ValueError("trade_observation_ids must contain non-empty strings")
        if not isinstance(self.findings, tuple) or not all(isinstance(value, WalletTradeFinding) for value in self.findings):
            raise ValueError("findings must be a tuple of WalletTradeFinding values")
        if self.state is WalletTradeEpisodeState.CLOSED:
            if self.closed_at_unix_ms is None:
                raise ValueError("CLOSED episode requires closed_at_unix_ms")
            if self.counter_asset_mint is None:
                raise ValueError("CLOSED episode requires counter_asset_mint")
            if self.total_bought_quantity_raw <= 0 or self.total_sold_quantity_raw <= 0:
                raise ValueError("CLOSED episode requires positive bought and sold quantities")
            if self.remaining_quantity_raw != 0:
                raise ValueError("CLOSED episode requires zero remaining quantity")
            if self.total_entry_cost_counter_raw <= 0:
                raise ValueError("CLOSED episode requires positive entry cost")
            if self.estimated_realized_pnl_counter_raw is None or self.estimated_return_pct is None:
                raise ValueError("CLOSED episode requires estimated outcome")
        else:
            if self.closed_at_unix_ms is not None:
                raise ValueError("non-CLOSED episode cannot have closed_at_unix_ms")
            if self.estimated_realized_pnl_counter_raw is not None or self.estimated_return_pct is not None:
                raise ValueError("OPEN/UNRESOLVED episode cannot carry estimated outcome")
            if self.state is WalletTradeEpisodeState.OPEN and self.remaining_quantity_raw <= 0:
                raise ValueError("OPEN episode requires positive remaining quantity")


@dataclass(frozen=True, slots=True)
class WalletTradeReconstruction:
    wallet: str
    candidate_mint: str
    as_of_unix_ms: int
    episodes: tuple[WalletTradeEpisode, ...]
    findings: tuple[WalletTradeFinding, ...]
    halted_on_uncertain_inventory: bool

    def __post_init__(self) -> None:
        _require_non_empty_string("wallet", self.wallet)
        _require_non_empty_string("candidate_mint", self.candidate_mint)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if not isinstance(self.episodes, tuple) or not all(isinstance(value, WalletTradeEpisode) for value in self.episodes):
            raise ValueError("episodes must be a tuple of WalletTradeEpisode values")
        if not isinstance(self.findings, tuple) or not all(isinstance(value, WalletTradeFinding) for value in self.findings):
            raise ValueError("findings must be a tuple of WalletTradeFinding values")
        if not isinstance(self.halted_on_uncertain_inventory, bool):
            raise ValueError("halted_on_uncertain_inventory must be boolean")
        for expected_index, episode in enumerate(self.episodes):
            if episode.wallet != self.wallet or episode.candidate_mint != self.candidate_mint:
                raise ValueError("episode wallet/mint must match reconstruction")
            if episode.episode_index != expected_index:
                raise ValueError("episode indexes must be contiguous from zero")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_optional_non_empty_string(name: str, value: object | None) -> None:
    if value is not None:
        _require_non_empty_string(name, value)


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_optional_non_negative_int(name: str, value: object | None) -> None:
    if value is not None:
        _require_non_negative_int(name, value)


def _require_optional_int(name: str, value: object | None) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise ValueError(f"{name} must be an integer or None")
