from __future__ import annotations

import json
import os
from pathlib import Path

from .codec import (
    build_artifact_document,
    canonical_json,
    compute_artifact_fingerprint,
    decode_artifact_document,
)
from .models import TrainedLogisticRegressionModel


class ModelArtifactStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.name:
            raise ValueError("model artifact path must name a file")

    def load(self) -> tuple[TrainedLogisticRegressionModel, ...]:
        if not self.path.exists():
            return ()
        try:
            raw = self.path.read_text(encoding="utf-8")
            document = json.loads(raw)
            return decode_artifact_document(document)
        except (OSError, json.JSONDecodeError, TypeError, KeyError, ValueError) as error:
            raise ValueError(f"model artifact file is invalid: {error}") from error

    def get(self, model_version: str) -> TrainedLogisticRegressionModel | None:
        if not isinstance(model_version, str) or not model_version.strip():
            raise ValueError("model_version must be a non-empty string")
        for model in self.load():
            if model.model_version == model_version:
                return model
        return None

    def append(
        self,
        model: TrainedLogisticRegressionModel,
    ) -> tuple[TrainedLogisticRegressionModel, ...]:
        if type(model) is not TrainedLogisticRegressionModel:
            raise ValueError("model must be an exact TrainedLogisticRegressionModel")
        compute_artifact_fingerprint(model)

        current = self.load()
        for existing in current:
            if existing.model_version == model.model_version:
                if existing == model:
                    return current
                raise ValueError(
                    "model_version is already stored with different content"
                )

        updated = current + (model,)
        self._write(updated)
        return updated

    def _write(self, models: tuple[TrainedLogisticRegressionModel, ...]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        payload = canonical_json(build_artifact_document(models)) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
