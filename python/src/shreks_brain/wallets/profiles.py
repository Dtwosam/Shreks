from __future__ import annotations

from shreks_brain.regime import MarketRegime

from .models import (
    WalletTradeEpisode,
    WalletTradeEpisodeState,
    WalletTradeEvidenceQuality,
    WalletTradeReconstruction,
)
from .profile_models import (
    WalletEpisodeProfileContext,
    WalletProfile,
    WalletProfilePolicy,
    WalletRegimeProfile,
)


_EPISODE_ID = tuple[str, int]
_REGIME_ORDER = (
    MarketRegime.HOT,
    MarketRegime.NORMAL,
    MarketRegime.WEAK,
    MarketRegime.DEAD,
)


def build_wallet_profile(
    *,
    wallet: str,
    as_of_unix_ms: int,
    reconstructions: tuple[WalletTradeReconstruction, ...],
    contexts: tuple[WalletEpisodeProfileContext, ...],
    policy: WalletProfilePolicy,
) -> WalletProfile:
    _require_non_empty_string("wallet", wallet)
    _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)
    if not isinstance(policy, WalletProfilePolicy):
        raise ValueError("policy must be a WalletProfilePolicy")
    if not isinstance(reconstructions, tuple) or not all(
        isinstance(value, WalletTradeReconstruction) for value in reconstructions
    ):
        raise ValueError(
            "reconstructions must be a tuple of WalletTradeReconstruction values"
        )
    if not isinstance(contexts, tuple) or not all(
        isinstance(value, WalletEpisodeProfileContext) for value in contexts
    ):
        raise ValueError(
            "contexts must be a tuple of WalletEpisodeProfileContext values"
        )

    candidate_mints: set[str] = set()
    episodes: list[WalletTradeEpisode] = []
    closed: dict[_EPISODE_ID, WalletTradeEpisode] = {}
    all_episode_states: dict[_EPISODE_ID, WalletTradeEpisodeState] = {}
    halted_count = 0

    for reconstruction in reconstructions:
        if reconstruction.wallet != wallet:
            raise ValueError("reconstruction wallet must match profile wallet")
        if reconstruction.as_of_unix_ms != as_of_unix_ms:
            raise ValueError("reconstruction as_of_unix_ms must match profile as_of")
        if reconstruction.candidate_mint in candidate_mints:
            raise ValueError("duplicate reconstruction candidate mint")
        candidate_mints.add(reconstruction.candidate_mint)
        if reconstruction.halted_on_uncertain_inventory:
            halted_count += 1

        for episode in reconstruction.episodes:
            if (
                episode.opened_at_unix_ms > as_of_unix_ms
                or episode.last_observed_at_unix_ms > as_of_unix_ms
                or (
                    episode.closed_at_unix_ms is not None
                    and episode.closed_at_unix_ms > as_of_unix_ms
                )
            ):
                raise ValueError("future episode evidence is not allowed")
            identity = (reconstruction.candidate_mint, episode.episode_index)
            episodes.append(episode)
            all_episode_states[identity] = episode.state
            if episode.state is WalletTradeEpisodeState.CLOSED:
                closed[identity] = episode

    closed_episodes = tuple(closed.values())
    open_count = sum(
        episode.state is WalletTradeEpisodeState.OPEN for episode in episodes
    )
    unresolved_count = sum(
        episode.state is WalletTradeEpisodeState.UNRESOLVED for episode in episodes
    )

    direct_count = sum(
        episode.evidence_quality is WalletTradeEvidenceQuality.DIRECT
        for episode in closed_episodes
    )
    mixed_count = sum(
        episode.evidence_quality is WalletTradeEvidenceQuality.MIXED
        for episode in closed_episodes
    )
    inferred_count = sum(
        episode.evidence_quality is WalletTradeEvidenceQuality.INFERRED
        for episode in closed_episodes
    )

    closed_weighted = tuple(
        (episode, _episode_weight(episode, policy))
        for episode in closed_episodes
    )
    effective_sample = sum(weight for _, weight in closed_weighted)
    evidence_confidence = min(
        effective_sample / policy.full_confidence_effective_sample_size,
        1.0,
    )

    return_median = _weighted_median(
        (
            (episode.estimated_return_pct, weight, _episode_identity(episode))
            for episode, weight in closed_weighted
            if episode.estimated_return_pct is not None
        )
    )
    win_rate = _weighted_rate(
        (
            (episode.estimated_return_pct > 0.0, weight)
            for episode, weight in closed_weighted
            if episode.estimated_return_pct is not None
        )
    )
    hold_median = _weighted_median(
        (
            (
                float(episode.closed_at_unix_ms - episode.opened_at_unix_ms),
                weight,
                _episode_identity(episode),
            )
            for episode, weight in closed_weighted
            if episode.closed_at_unix_ms is not None
        )
    )

    aggregate_mint, aggregate_pnl = _aggregate_raw_pnl(closed_episodes)

    context_version, context_rows = _validate_contexts(
        wallet=wallet,
        as_of_unix_ms=as_of_unix_ms,
        contexts=contexts,
        closed=closed,
        all_episode_states=all_episode_states,
        policy=policy,
    )

    entry_quality_rows = tuple(
        (context.entry_quality_pct, weight, identity)
        for context, episode, weight, identity in context_rows
        if context.entry_quality_pct is not None
    )
    entry_timing_rows = tuple(
        (
            float(context.entry_delay_from_candidate_discovery_ms),
            weight,
            identity,
        )
        for context, episode, weight, identity in context_rows
        if context.entry_delay_from_candidate_discovery_ms is not None
    )
    drawdown_rows = tuple(
        (context.max_drawdown_pct, weight, identity)
        for context, episode, weight, identity in context_rows
        if context.max_drawdown_pct is not None
    )
    rug_rows = tuple(
        (context.rug_exposed, weight)
        for context, episode, weight, identity in context_rows
        if context.rug_exposed is not None
    )

    regime_rows = tuple(
        (context, episode, weight, identity)
        for context, episode, weight, identity in context_rows
        if context.regime is not None
    )
    regime_profiles = _build_regime_profiles(regime_rows)

    return WalletProfile(
        wallet=wallet,
        as_of_unix_ms=as_of_unix_ms,
        policy_version=policy.version,
        context_version=context_version,
        reconstruction_count=len(reconstructions),
        episode_count=len(episodes),
        closed_episode_count=len(closed_episodes),
        open_episode_count=open_count,
        unresolved_episode_count=unresolved_count,
        halted_reconstruction_count=halted_count,
        direct_closed_episode_count=direct_count,
        mixed_closed_episode_count=mixed_count,
        inferred_closed_episode_count=inferred_count,
        effective_closed_sample_size=effective_sample,
        evidence_sample_confidence=evidence_confidence,
        confidence_weighted_median_return_pct=return_median,
        confidence_weighted_win_rate=win_rate,
        confidence_weighted_median_hold_ms=hold_median,
        aggregate_pnl_counter_asset_mint=aggregate_mint,
        aggregate_realized_pnl_counter_raw=aggregate_pnl,
        entry_quality_sample_count=len(entry_quality_rows),
        confidence_weighted_median_entry_quality_pct=_weighted_median(
            entry_quality_rows
        ),
        entry_timing_sample_count=len(entry_timing_rows),
        confidence_weighted_median_entry_delay_ms=_weighted_median(
            entry_timing_rows
        ),
        drawdown_sample_count=len(drawdown_rows),
        confidence_weighted_median_max_drawdown_pct=_weighted_median(
            drawdown_rows
        ),
        rug_exposure_sample_count=len(rug_rows),
        confidence_weighted_rug_exposure_rate=_weighted_rate(rug_rows),
        regime_sample_count=len(regime_rows),
        regime_profiles=regime_profiles,
    )


def _episode_weight(
    episode: WalletTradeEpisode, policy: WalletProfilePolicy
) -> float:
    if episode.evidence_quality is WalletTradeEvidenceQuality.DIRECT:
        return float(policy.direct_episode_weight)
    if episode.evidence_quality is WalletTradeEvidenceQuality.MIXED:
        return float(policy.mixed_episode_weight)
    if episode.evidence_quality is WalletTradeEvidenceQuality.INFERRED:
        return float(policy.inferred_episode_weight)
    raise ValueError("unsupported wallet trade evidence quality")


def _episode_identity(episode: WalletTradeEpisode) -> _EPISODE_ID:
    return (episode.candidate_mint, episode.episode_index)


def _weighted_median(rows: object) -> float | None:
    positive: list[tuple[float, float, _EPISODE_ID]] = []
    for value, weight, identity in rows:  # type: ignore[misc]
        if weight <= 0.0:
            continue
        positive.append((float(value), float(weight), identity))
    if not positive:
        return None
    positive.sort(key=lambda item: (item[0], item[2]))
    total = sum(item[1] for item in positive)
    threshold = total / 2.0
    cumulative = 0.0
    for value, weight, _ in positive:
        cumulative += weight
        if cumulative >= threshold:
            return value
    raise AssertionError("weighted median cumulative weight did not reach threshold")


def _weighted_rate(rows: object) -> float | None:
    total = 0.0
    positive = 0.0
    for outcome, weight in rows:  # type: ignore[misc]
        weight_value = float(weight)
        if weight_value <= 0.0:
            continue
        total += weight_value
        if bool(outcome):
            positive += weight_value
    if total == 0.0:
        return None
    return positive / total


def _aggregate_raw_pnl(
    closed_episodes: tuple[WalletTradeEpisode, ...],
) -> tuple[str | None, int | None]:
    if not closed_episodes:
        return None, None
    counter_mints = {episode.counter_asset_mint for episode in closed_episodes}
    if len(counter_mints) != 1:
        return None, None
    counter_mint = next(iter(counter_mints))
    if counter_mint is None:
        return None, None
    raw_values = tuple(
        episode.estimated_realized_pnl_counter_raw for episode in closed_episodes
    )
    if any(value is None for value in raw_values):
        return None, None
    return counter_mint, sum(value for value in raw_values if value is not None)


def _validate_contexts(
    *,
    wallet: str,
    as_of_unix_ms: int,
    contexts: tuple[WalletEpisodeProfileContext, ...],
    closed: dict[_EPISODE_ID, WalletTradeEpisode],
    all_episode_states: dict[_EPISODE_ID, WalletTradeEpisodeState],
    policy: WalletProfilePolicy,
) -> tuple[
    str | None,
    tuple[
        tuple[
            WalletEpisodeProfileContext,
            WalletTradeEpisode,
            float,
            _EPISODE_ID,
        ],
        ...,
    ],
]:
    identities: set[_EPISODE_ID] = set()
    versions: set[str] = set()
    rows: list[
        tuple[
            WalletEpisodeProfileContext,
            WalletTradeEpisode,
            float,
            _EPISODE_ID,
        ]
    ] = []

    for context in contexts:
        if context.wallet != wallet:
            raise ValueError("context wallet must match profile wallet")
        identity = (context.candidate_mint, context.episode_index)
        if identity in identities:
            raise ValueError("duplicate context identity")
        identities.add(identity)

        episode = closed.get(identity)
        if episode is None:
            state = all_episode_states.get(identity)
            if state is None:
                raise ValueError("context must target an existing CLOSED episode")
            raise ValueError(
                f"context must target a CLOSED episode, not {state.value}"
            )
        assert episode.closed_at_unix_ms is not None
        if context.observed_at_unix_ms < episode.closed_at_unix_ms:
            raise ValueError("context observation cannot be before episode closed")
        if context.observed_at_unix_ms > as_of_unix_ms:
            raise ValueError("future context evidence is not allowed")

        versions.add(context.context_version)
        if len(versions) > 1:
            raise ValueError("context_version must be identical across a profile")

        rows.append(
            (context, episode, _episode_weight(episode, policy), identity)
        )

    context_version = next(iter(versions)) if versions else None
    return context_version, tuple(rows)


def _build_regime_profiles(
    rows: tuple[
        tuple[
            WalletEpisodeProfileContext,
            WalletTradeEpisode,
            float,
            _EPISODE_ID,
        ],
        ...,
    ]
) -> tuple[WalletRegimeProfile, ...]:
    result: list[WalletRegimeProfile] = []
    for regime in _REGIME_ORDER:
        selected = tuple(
            (context, episode, weight, identity)
            for context, episode, weight, identity in rows
            if context.regime is regime
        )
        if not selected:
            continue
        effective = sum(weight for _, _, weight, _ in selected)
        median_return = _weighted_median(
            (
                (episode.estimated_return_pct, weight, identity)
                for _, episode, weight, identity in selected
                if episode.estimated_return_pct is not None
            )
        )
        win_rate = _weighted_rate(
            (
                (episode.estimated_return_pct > 0.0, weight)
                for _, episode, weight, _ in selected
                if episode.estimated_return_pct is not None
            )
        )
        result.append(
            WalletRegimeProfile(
                regime=regime,
                closed_episode_count=len(selected),
                effective_sample_size=effective,
                confidence_weighted_median_return_pct=median_return,
                confidence_weighted_win_rate=win_rate,
            )
        )
    return tuple(result)


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
