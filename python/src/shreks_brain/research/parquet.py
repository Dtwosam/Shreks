from __future__ import annotations

from pathlib import Path

from .models import ResearchDatasetManifest, ResearchSnapshotInputs


def write_research_parquet(
    snapshots: tuple[ResearchSnapshotInputs, ...],
    path: str | Path,
) -> ResearchDatasetManifest:
    raise NotImplementedError("D6 Parquet writer is not implemented yet")
