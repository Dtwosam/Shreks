from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

from shreks_brain.fast_campaign_paper import FastDeterministicPaperPosture
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicCandidateManifest,
    FastDeterministicLifecycleDecision,
)
from shreks_brain.research.fast_training_features import FastTrainingFeatureRecord

from .codec import (
    build_fast_deterministic_row_request,
    decode_fast_deterministic_row_result,
)
from .models import FastOfflineRowEvidence


def evaluate_fast_deterministic_row_offline(
    *,
    binary_path: str | Path,
    record: FastTrainingFeatureRecord,
    manifest: FastDeterministicCandidateManifest,
    posture: FastDeterministicPaperPosture,
    evidence: FastOfflineRowEvidence,
) -> FastDeterministicLifecycleDecision:
    request = build_fast_deterministic_row_request(
        record=record,
        manifest=manifest,
        posture=posture,
        evidence=evidence,
    )
    binary = Path(binary_path)
    if not str(binary).strip():
        raise ValueError("binary_path must be explicit and non-empty")
    if not binary.is_file():
        raise ValueError("binary_path must identify an existing file")

    request_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="shreks-fast-deterministic-row-",
            suffix=".json",
            delete=False,
        ) as handle:
            handle.write(request)
            request_path = Path(handle.name)

        completed = subprocess.run(
            [str(binary), str(request_path)],
            shell=False,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            stderr = completed.stderr[-2_000:].strip()
            detail = f": {stderr}" if stderr else ""
            raise RuntimeError(
                "offline deterministic row evaluator exited "
                f"{completed.returncode}{detail}"
            )
        if not completed.stdout:
            raise RuntimeError(
                "offline deterministic row evaluator returned empty stdout"
            )
        return decode_fast_deterministic_row_result(
            completed.stdout,
            manifest=manifest,
            record=record,
            posture=posture,
        )
    finally:
        if request_path is not None:
            request_path.unlink(missing_ok=True)
