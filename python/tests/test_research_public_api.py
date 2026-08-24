from shreks_brain import research


def test_research_public_api_is_exact():
    assert research.__all__ == (
        "RESEARCH_DATASET_SCHEMA_VERSION",
        "RESEARCH_OUTCOME_HORIZONS_SECONDS",
        "RESEARCH_FEATURE_COLUMNS",
        "RESEARCH_LABEL_COLUMNS",
        "ResearchOutcomeLabelStatus",
        "ResearchExitability",
        "ResearchOutcomeLabel",
        "ResearchSnapshotInputs",
        "ResearchDatasetManifest",
        "build_research_row",
        "build_research_dataset",
        "write_research_parquet",
    )
    assert research.RESEARCH_DATASET_SCHEMA_VERSION == "d6-research-v1"
    assert research.RESEARCH_OUTCOME_HORIZONS_SECONDS == (
        60,
        300,
        900,
        1800,
        3600,
        14_400,
        86_400,
    )
