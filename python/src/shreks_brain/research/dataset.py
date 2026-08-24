from __future__ import annotations

from .models import ResearchSnapshotInputs


RESEARCH_FEATURE_COLUMNS: tuple[str, ...] = ()
RESEARCH_LABEL_COLUMNS: tuple[str, ...] = ()


def build_research_row(inputs: ResearchSnapshotInputs) -> dict[str, object]:
    raise NotImplementedError("D6 logical row builder is not implemented yet")


def build_research_dataset(
    snapshots: tuple[ResearchSnapshotInputs, ...],
) -> tuple[dict[str, object], ...]:
    raise NotImplementedError("D6 logical dataset builder is not implemented yet")
