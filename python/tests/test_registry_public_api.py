import shreks_brain.registry as registry


def test_registry_public_api_is_deliberately_small() -> None:
    assert set(registry.__all__) == {
        "CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION",
        "ChampionChallengerRegistry",
        "RegistryCandidate",
        "RegistryEvaluationEvidence",
        "RegistryStatus",
        "RegistryStatusEvent",
        "RegistryStore",
        "build_registry_candidate",
    }


def test_registry_public_api_has_no_automatic_promotion_surface() -> None:
    forbidden = {
        "auto_promote",
        "promote_if_profitable",
        "select_champion",
        "promotion_threshold",
        "enable_live",
    }
    assert forbidden.isdisjoint(set(dir(registry)))
