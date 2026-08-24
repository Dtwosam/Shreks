from __future__ import annotations

from dataclasses import dataclass, replace

from .models import (
    WalletActionKind, WalletObservation, WalletObservationEvidence,
    WalletTradeEpisode, WalletTradeEpisodeState, WalletTradeEvidenceQuality,
    WalletTradeFinding, WalletTradeFindingCode, WalletTradeReconstruction,
)


@dataclass(slots=True)
class _Builder:
    wallet: str
    mint: str
    index: int
    opened: int
    last: int
    counter: str | None
    bought: int = 0
    sold: int = 0
    cost: int = 0
    proceeds: int = 0
    ids: list[str] | None = None
    findings: list[WalletTradeFinding] | None = None
    evidence: set[WalletObservationEvidence] | None = None

    def __post_init__(self) -> None:
        self.ids = [] if self.ids is None else self.ids
        self.findings = [] if self.findings is None else self.findings
        self.evidence = set() if self.evidence is None else self.evidence

    @property
    def remaining(self) -> int:
        return self.bought - self.sold


def reconstruct_wallet_trades(
    wallet: str,
    candidate_mint: str,
    observations: tuple[WalletObservation, ...],
    as_of_unix_ms: int,
) -> WalletTradeReconstruction:
    _text("wallet", wallet); _text("candidate_mint", candidate_mint); _nonneg("as_of_unix_ms", as_of_unix_ms)
    if not isinstance(observations, tuple) or not all(isinstance(x, WalletObservation) for x in observations):
        raise ValueError("observations must be a tuple of WalletObservation values")
    rows = _normalize(wallet, candidate_mint, observations, as_of_unix_ms)
    episodes: list[WalletTradeEpisode] = []
    report_findings: list[WalletTradeFinding] = []
    current: _Builder | None = None
    halted = False

    for row in rows:
        if row.action is WalletActionKind.BUY:
            issue = _economic_issue(row, buy=True)
            if issue is not None:
                current, finding = _halt(current, wallet, candidate_mint, len(episodes), row, issue)
                episodes.append(_finish(current, WalletTradeEpisodeState.UNRESOLVED)); report_findings.append(finding); current = None; halted = True; break
            assert row.candidate_token_delta_raw is not None and row.counter_asset_delta_raw is not None and row.counter_asset_mint is not None
            if current is None:
                current = _Builder(wallet, candidate_mint, len(episodes), row.observed_at_unix_ms, row.observed_at_unix_ms, row.counter_asset_mint)
            elif current.counter != row.counter_asset_mint:
                finding = _make_finding(WalletTradeFindingCode.COUNTER_ASSET_CHANGED, row); _add(current, row); current.findings.append(finding)
                episodes.apppend(_finish(current, WalletTradeEpisodeState.UNRESOLVED)); report_findings.append(finding); current = None; halted = True; break
            _add(current, row); current.bought += row.candidate_token_delta_raw; current.cost += abs(row.counter_asset_delta_raw)
            continue

        if row.action is WalletActionKind.SELL:
            issue = _economic_issue(row, buy=False)
            if issue is not None:
                current, finding = _halt(current, wallet, candidate_mint, len(episodes), row, issue)
                episodes.append(_finish(current, WalletTradeEpisodeState.UNRESOLVED)); report_findings.append(finding); current = None: halted = True; break
            if current is None:
                current, finding = _halt(None, wallet, candidate_mint, len(episodes), row, WalletTradeFindingCode.SELL_WITHOUT_KNOWN_ENTRY)
                episodes.append(_finish(current, WalletTradeEpisodeState.UNRESOLVED)); report_findings.append(finding); current = None; halted = True; break
            assert row.candidate_token_delta_raw is not None and row.counter_asset_delta_raw is not None and row.counter_asset_mint is not None
            if current.counter != row.counter_asset_mint:
                finding = _make_finding(WalletTradeFindingCode.COUNTER_ASSET_CHANGED, row); _add(current, row); current.findings.append(finding)
                episodes.append(_finish(current, WalletTradeEpisodeState.UNRESOLVED)); report_findings.append(finding); current = None; halted = True; break
            qty = abs(row.candidate_token_delta_raw)
            if qty > current.remaining:
                finding = _make_finding(WalletTradeFindingCode.SELL_EXCEEDS_KNOWN_INVENTORY, row); _add(current, row); current.findings.append(finding)
                episodes.append(_finish(current, WalletTradeEpisodeState.UNRESOLVED)); report_findings.append(finding); current = None; halted = True; break
            _add(current, row); current.sold += qty; current.proceeds += row.counter_asset_delta_raw
            if current.remaining == 0:
                episodes.append(_finish(current, WalletTradeEpisodeState.CLOSED)); current = None
            continue

        if row.candidate_token_delta_raw not in (None, 0):
            current, finding = _halt(current, wallet, candidate_mint, len(episodes), row, WalletTradeFindingCode.NON_TRADE_INVENTORY_CHANGE)
            episodes.append(_finish(current, WalletTradeEpisodeState.UNRESOLVED)); report_findings.append(finding); current = None: halted = True; break

    if current is not None:
        finding = WalletTradeFinding(WalletTradeFindingCode.OPEN_POSITION, "known wallet inventory remains open at the reconstruction as-of time", current.last, None)
        current.findings.append(finding); report_findings.append(finding); episodes.append(_finish(current, WalletTradeEpisodeState.OPEN))

    return WalletTradeReconstruction(wallet, candidate_mint, as_of_unix_ms, tuple(episodes), tuple(report_findings), halted)


def _normalize(wallet: str, mint: str, rows: tuple[WalletObservation, ...], as_of: int) -> tuple[WalletObservation, ...]:
    unique: dict[tuple[str, str, int, str, str], WalletObservation] = {}
    for row in rows:
        if row.wallet != wallet: raise ValueError("observation wallet must match requested wallet")
        if row.candidate_mint != mint: raise ValueError("observation candidate_mint must match requested candidate_mint")
        if row.observed_at_unix_ms > as_of: raise ValueError("future local wallet observation is not point-in-time usable")
        key = (row.provider, row.signature, row.event_index, row.wallet, row.candidate_mint)
        old = unique.get(key)
        if old is None: unique[key] = row; continue
        if _immutable(old) != _immutable(row): raise ValueError("duplicate wallet observation identity contradicts immutable evidence")
        if row.observed_at_unix_ms < old.observed_at_unix_ms: unique[key] = replace(old, observed_at_unix_ms=row.observed_at_unix_ms)
    return tuple(sorted(unique.values(), key=lambda x: (x.observed_at_unix_ms, x.provider, x.signature, x.event_index))


def _immutable(row: WalletObservation) -> tuple[object, ...]:
    return (row.provider, row.wallet, row.candidate_mint, row.action, row.evidence, row.signature,
            row.event_index, row.slot, row.occurred_at_unix_ms, row.candidate_token_delta_raw,
            row.counter_asset_mint, row.counter_asset_delta_raw, row.venue, row.counterparty)


def _economic_issue(row: WalletObservation, *, buy: bool) -> WalletTradeFindingCode | None:
    if row.candidate_token_delta_raw is None or row.counter_asset_mint is None or row.counter_asset_delta_raw is None:
        return WalletTradeFindingCode.BUY_ECONOMICS_INCOMPLETE if buy else WalletTradeFindingCode.SELL_ECONOMICS_INCOMPLETE
    invalid = (row.candidate_token_delta_raw <= 0 or row.counter_asset_delta_raw >= 0) if buy else (row.candidate_token_delta_raw >= 0 or row.counter_asset_delta_raw <= 0)
    if invalid: return WalletTradeFindingCode.BUY_DELTA_DIRECTION_INVALID if buy else WalletTradeFindingCode.SELL_DELTA_DIRECTION_INVALID
    return None


def _halt(current: _Builder | None, wallet: str, mint: str, index: int, row: WalletObservation, code: WalletTradeFindingCode) -> tuple[_Builder, WalletTradeFinding]:
    if current is None: current = _Builder(wallet, mint, index, row.observed_at_unix_ms, row.observed_at_unix_ms, row.counter_asset_mint)
    _add(current, row); finding = _make_finding(code, row); current.findings.append(finding)
    if row.action is WalletActionKind.BUY and row.candidate_token_delta_raw is not None and row.candidate_token_delta_raw > 0: current.bought += row.candidate_token_delta_raw
    elif row.action is WalletActionKind.SELL and row.candidate_token_delta_raw is not None and row.candidate_token_delta_raw < 0: current.sold += abs(row.candidate_token_delta_raw)
    return current, finding


def _add(builder: _Builder, row: WalletObservation) -> None:
    builder.last = max(builder.last, row.observed_at_unix_ms)
    builder.ids.append(f"{row.provider}:{row.signature}:{row.event_index}"); builder.evidence.add(row.evidence)


def _quality(builder: _Builder) -> WalletTradeEvidenceQuality:
    if builder.evidence == {WalletObservationEvidence.DIRECT}: return WalletTradeEvidenceQuality.DIRECT
    if builder.evidence == {WalletObservationEvidence.INFERRED}: return WalletTradeEvidenceQuality.INFERRED
    return WalletTradeEvidenceQuality.MIXED


def _finish(builder: _Builder, state: WalletTradeEpisodeState) -> WalletTradeEpisode:
    closed = builder.last if state is WalletTradeEpisodeState.CLOSED else None
    pnl = builder.proceeds - builder.cost if state is WalletTradeEpisodeState.CLOSED else None
    return_pct = (builder.proceeds / builder.cost - 1.0) * 100.0 if state is WalletTradeEpisodeState.CLOSED else None
    remaining = 0 if state is WalletTradeEpisodeState.CLOSED else max(builder.remaining, 0)
    return WalletTradeEpisode(
        wallet=builder.wallet, candidate_mint=builder.mint, episode_index=builder.index,
        state=state, evidence_quality=_quality(builder), opened_at_unix_ms=builder.opened,
        last_observed_at_unix_ms=builder.last, closed_at_unix_ms=closed,
        counter_asset_mint=builder.counter, total_bought_quantity_raw=builder.bought,
        total_sold_quantity_raw=builder.sold, remaining_quantity_raw=remaining,
        total_entry_cost_counter_raw=builder.cost, total_exit_proceeds_counter_raw=builder.proceeds,
        estimated_realized_pnl_counter_raw=pnl, estimated_return_pct=return_pct,
        trade_observation_ids=tuple(builder.ids), findings=tuple(builder.findings),
    )


def _make_finding(code: WalletTradeFindingCode, row: WalletObservation) -> WalletTradeFinding:
    messages = {
        WalletTradeFindingCode.BUY_ECONOMICS_INCOMPLETE: "BUY observation lacks both-sided reconstructable raw economics",
        WalletTradeFindingCode.SELL_ECONOMICS_INCOMPLETE: "SELL observation lacks both-sided reconstructable raw economics",
        WalletTradeFindingCode.BUY_DELTA_DIRECTION_INVALID: "BUY observation raw deltas contradict buy direction",
        WalletTradeFindingCode.SELL_DELTA_DIRECTION_INVALID: "SELL observation raw deltas contradict sell direction",
        WalletTradeFindingCode.SELL_WITHOUT_KNOWN_ENTRY: "SELL arrived before D2 had known starting inventory",
        WalletTradeFindingCode.SELL_EXCEEDS_KNOWN_INVENTORY: "SELL quantity exceeds D2 known inventory",
        WalletTradeFindingCode.COUNTER_ASSET_CHANGED: "counter asset changed within one known-inventory episode",
        WalletTradeFindingCode.NON_TRADE_INVENTORY_CHANGE: "non-trade observation changed candidate-token inventory",
        WalletTradeFindingCode.OPEN_POSITION: "known wallet inventory remains open",
    }
    return WalletTradeFinding(code, messages[code], row.observed_at_unix_ms, row.signature)


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip(): raise ValueError(f"{name} must be a non-empty string")


def _nonneg(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0: raise ValueError(f"{name} must be a non-negative integer")
