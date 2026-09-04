from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

from shreks_brain.fast_campaign import (
    FastCampaignDecisionBatch,
    FastCampaignDecisionResults,
    decode_fast_campaign_decision_results,
    encode_fast_campaign_decision_batch,
)


def evaluate_fast_campaign_decision_batch_offline(
    *,
    binary_path: str | Path,
    champion_path: str | Path,
    batch: FastCampaignDecisionBatch,
) -> FastCampaignDecisionResults:
    if type(batch) is not FastCampaignDecisionBatch:
        raise ValueError("batch must be exact FastCampaignDecisionBatch")
    binary = _source_file(binary_path, "binary_path")
    champion = _source_file(champion_path, "champion_path")
    payload = encode_fast_campaign_decision_batch(batch)

    request_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="shreks-fast-learned-campaign-",
            suffix=".json",
            delete=False,
        ) as handle:
            handle.write(payload)
            request_path = Path(handle.name)

        completed = subprocess.run(
            [str(binary), str(champion), str(request_path)],
            shell=False,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            stderr = completed.stderr[-2_000:].strip()
            detail = f": {stderr}" if stderr else ""
            raise RuntimeError(
                "offline learned campaign decision process exited "
                f"{completed.returncode}{detail}"
            )
        if not completed.stdout:
            raise RuntimeError(
                "offline learned campaign decision process returned empty stdout"
            )
        results = decode_fast_campaign_decision_results(
            completed.stdout
        )
        _require_population_alignment(batch, results)
        return results
    finally:
        if request_path is not None:
            request_path.unlink(missing_ok=True)


def _require_population_alignment(
    batch: FastCampaignDecisionBatch,
    results: FastCampaignDecisionResults,
) -> None:
    if len(results.decisions) != len(batch.decisions):
        raise ValueError(
            "learned campaign result population length mismatch"
        )
    for index, (request, result) in enumerate(
        zip(batch.decisions, results.decisions)
    ):
        expected = (
            request.source_event_id,
            request.market_key,
            request.source_sequence,
            request.as_of_unix_ms,
        )
        actual = (
            result.source_event_id,
            result.market_key,
            result.source_sequence,
            result.as_of_unix_ms,
        )
        if actual != expected:
            raise ValueError(
                f"learned campaign result population identity mismatch at index {index}"
            )
        if result.policy_version != batch.policy.version:
            raise ValueError(
                f"learned campaign result policy version mismatch at index {index}"
            )


def _source_file(
    value: str | Path,
    name: str,
) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError(f"{name} must be a string or Path")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{name} must be explicit and non-empty")
    path = Path(value)
    if not path.is_file():
        raise ValueError(f"{name} must identify an existing file")
    return path
