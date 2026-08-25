from __future__ import annotations

from pathlib import Path

import pytest

from shreks_brain.observer_campaign.runtime_config import (
    ObserverPaperCampaignRuntimeConfig,
    ObserverPaperCampaignRuntimeConfigError,
    load_observer_paper_campaign_runtime_config,
)


VALID_ENV = {
    "SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH": "state/observer.sqlite",
    "SHREKS_PAPER_CAMPAIGN_E11_PATH": "evidence/e11.json",
    "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH": "config/paper-campaign.json",
    "SHREKS_PAPER_CAMPAIGN_INTERVAL_SECONDS": "2.5",
}


def test_runtime_config_loads_only_operational_values_and_resolves_relative_paths(
    tmp_path: Path,
) -> None:
    config = load_observer_paper_campaign_runtime_config(
        VALID_ENV,
        base_directory=tmp_path,
    )

    assert config == ObserverPaperCampaignRuntimeConfig(
        observer_database_path=(tmp_path / "state/observer.sqlite").resolve(),
        evidence_path=(tmp_path / "evidence/e11.json").resolve(),
        manifest_path=(tmp_path / "config/paper-campaign.json").resolve(),
        cycle_interval_seconds=2.5,
        max_cycles=None,
    )


def test_runtime_config_preserves_absolute_paths_and_accepts_positive_cycle_limit(
    tmp_path: Path,
) -> None:
    env = dict(VALID_ENV)
    env.update(
        {
            "SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH": str(
                (tmp_path / "observer.sqlite").resolve()
            ),
            "SHREKS_PAPER_CAMPAIGN_E11_PATH": str((tmp_path / "e11.json").resolve()),
            "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH": str(
                (tmp_path / "manifest.json").resolve()
            ),
            "SHREKS_PAPER_CAMPAIGN_MAX_CYCLES": "3",
        }
    )

    config = load_observer_paper_campaign_runtime_config(
        env,
        base_directory=tmp_path / "ignored",
    )

    assert config.observer_database_path == (tmp_path / "observer.sqlite").resolve()
    assert config.evidence_path == (tmp_path / "e11.json").resolve()
    assert config.manifest_path == (tmp_path / "manifest.json").resolve()
    assert config.max_cycles == 3


@pytest.mark.parametrize(
    "missing_key",
    (
        "SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH",
        "SHREKS_PAPER_CAMPAIGN_E11_PATH",
        "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH",
        "SHREKS_PAPER_CAMPAIGN_INTERVAL_SECONDS",
    ),
)
def test_runtime_config_requires_every_operational_value(missing_key: str, tmp_path: Path) -> None:
    env = dict(VALID_ENV)
    env.pop(missing_key)

    with pytest.raises(ObserverPaperCampaignRuntimeConfigError, match="required"):
        load_observer_paper_campaign_runtime_config(env, base_directory=tmp_path)


@pytest.mark.parametrize(
    "value",
    ("", "0", "-1", "nan", "inf", "-inf", "not-a-number"),
)
def test_runtime_config_rejects_invalid_cycle_interval(value: str, tmp_path: Path) -> None:
    env = dict(VALID_ENV)
    env["SHREKS_PAPER_CAMPAIGN_INTERVAL_SECONDS"] = value

    with pytest.raises(ObserverPaperCampaignRuntimeConfigError, match="interval"):
        load_observer_paper_campaign_runtime_config(env, base_directory=tmp_path)


@pytest.mark.parametrize("value", ("0", "-1", "1.5", "nan", "inf", "three"))
def test_runtime_config_rejects_nonpositive_or_noninteger_cycle_limit(
    value: str,
    tmp_path: Path,
) -> None:
    env = dict(VALID_ENV)
    env["SHREKS_PAPER_CAMPAIGN_MAX_CYCLES"] = value

    with pytest.raises(ObserverPaperCampaignRuntimeConfigError, match="cycle"):
        load_observer_paper_campaign_runtime_config(env, base_directory=tmp_path)


def test_blank_optional_cycle_limit_means_unbounded_runtime(tmp_path: Path) -> None:
    env = dict(VALID_ENV)
    env["SHREKS_PAPER_CAMPAIGN_MAX_CYCLES"] = ""

    config = load_observer_paper_campaign_runtime_config(env, base_directory=tmp_path)

    assert config.max_cycles is None


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "SHREKS_PAPER_CAMPAIGN_STARTING_CAPITAL_USD",
        "SHREKS_PAPER_CAMPAIGN_MAX_SLIPPAGE_BPS",
        "SHREKS_PAPER_CAMPAIGN_RISK_LIMIT_USD",
        "SHREKS_PAPER_CAMPAIGN_SAFETY_WEIGHT",
        "SHREKS_PAPER_CAMPAIGN_MAX_ENTRY_CANDIDATES",
    ),
)
def test_runtime_config_rejects_trading_policy_environment_channels(
    forbidden_key: str,
    tmp_path: Path,
) -> None:
    env = dict(VALID_ENV)
    env[forbidden_key] = "1"

    with pytest.raises(ObserverPaperCampaignRuntimeConfigError, match="unsupported"):
        load_observer_paper_campaign_runtime_config(env, base_directory=tmp_path)


def test_runtime_config_ignores_unrelated_process_environment(tmp_path: Path) -> None:
    env = dict(VALID_ENV)
    env.update(
        {
            "PATH": "/usr/bin",
            "HOME": "/srv/shreks",
            "HELIUS_API_KEY": "not-consumed-by-this-runtime-config",
            "JUPITER_API_KEY": "not-consumed-by-this-runtime-config",
        }
    )

    config = load_observer_paper_campaign_runtime_config(env, base_directory=tmp_path)

    assert config.cycle_interval_seconds == 2.5
    assert not hasattr(config, "helius_api_key")
    assert not hasattr(config, "jupiter_api_key")
