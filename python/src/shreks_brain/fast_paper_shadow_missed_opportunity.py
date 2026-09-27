from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Mapping

from .fast_paper_runtime.codec import (
    read_fast_paper_runtime_manifest,
    verify_fast_paper_runtime_bindings,
)
from .fast_paper_runtime.shadow import (
    read_fast_paper_shadow_decision_evidence,
    validate_fast_paper_shadow_decision_evidence,
)
from .fast_paper_runtime.shadow_ledger import (
    build_fast_paper_shadow_ledger_binding,
)
from .fast_paper_shadow_sample_proof import (
    FAST_PAPER_SHADOW_SAMPLE_PROOF_SCHEMA_NAME,
    FAST_PAPER_SHADOW_SAMPLE_PROOF_SCHEMA_VERSION,
)
from .research.fast_training_targets import (
    load_future_path_training_labels_for_identities_from_sqlite,
)


FAST_PAPER_SHADOW_MISSED_OPPORTUNITY_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_missed_opportunity"
)
FAST_PAPER_SHADOW_MISSED_OPPORTUNITY_SCHEMA_VERSION = 1

_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EVIDENCE_NAME_RE = re.compile(
    r"^shadow-(?P<sequence>[0-9]{20})-(?P<digest>[0-9a-f]{16})\.json$"
)

_SAMPLE_REPORT_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "policy_version",
        "release_source_sha",
        "manifest_fingerprint_sha256",
        "champion_version",
        "champion_fingerprint_sha256",
        "action_policy_version",
        "binding_fingerprint_sha256",
        "window_since_unix_ms",
        "window_until_unix_ms",
        "window_duration_ms",
        "first_source_sequence",
        "last_source_sequence",
        "decision_count",
        "distinct_market_count",
        "distinct_mint_count",
        "observation_span_ms",
        "closed_position_count",
        "distinct_traded_mint_count",
        "distinct_buy_regime_count",
        "distinct_selected_horizon_count",
        "missing_buy_execution_source_count",
        "action_counts",
        "selected_horizon_counts",
        "buy_regime_counts",
        "gate_results",
        "decision",
        "promotion_authority",
        "production_paper_cutover",
        "signing_submission_authority",
        "live_authority",
        "report_fingerprint_sha256",
    }
)


class FastPaperShadowMissedOpportunityError(RuntimeError):
    pass


def collect_fast_paper_shadow_missed_opportunity(
    *,
    manifest_path: str | Path,
    ledger_database_path: str | Path,
    run_id: str,
    decision_evidence_directory: str | Path,
    sample_proof_path: str | Path,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
    future_path_label_version: int,
) -> dict[str, object]:
    expected_sha = _release_sha(expected_release_sha)
    since, until = _window(since_unix_ms, until_unix_ms)
    if not isinstance(run_id, str) or not run_id.strip():
        raise FastPaperShadowMissedOpportunityError(
            "missed-opportunity run id must be non-empty"
        )
    label_version = _positive_int(
        "future_path_label_version",
        future_path_label_version,
    )

    try:
        manifest = read_fast_paper_runtime_manifest(manifest_path)
        verify_fast_paper_runtime_bindings(manifest)
        binding = build_fast_paper_shadow_ledger_binding(
            manifest,
            run_id=run_id,
            database_path=ledger_database_path,
        )
    except Exception as exc:
        raise FastPaperShadowMissedOpportunityError(
            "missed-opportunity authority authentication failed"
        ) from exc
    if manifest.release_source_sha != expected_sha:
        raise FastPaperShadowMissedOpportunityError(
            "missed-opportunity release identity mismatch"
        )

    sample = _read_sample_proof(sample_proof_path)
    _require_sample_matches(
        sample,
        manifest=manifest,
        binding=binding,
        expected_release_sha=expected_sha,
        since_unix_ms=since,
        until_unix_ms=until,
    )

    decisions = _read_window_decisions(
        decision_evidence_directory,
        manifest=manifest,
        since_unix_ms=since,
        until_unix_ms=until,
    )
    if len(decisions) != sample["decision_count"]:
        raise FastPaperShadowMissedOpportunityError(
            "missed-opportunity decision count does not reconcile with FL11.1"
        )

    skips = tuple(
        evidence for evidence in decisions
        if evidence.decision.action == "SKIP"
    )
    for evidence in skips:
        if evidence.position.kind != "FLAT":
            raise FastPaperShadowMissedOpportunityError(
                "missed-opportunity SKIP decision must have FLAT posture"
            )

    horizons = tuple(manifest.action_policy.horizons_ms)
    if (
        not horizons
        or tuple(sorted(set(horizons))) != horizons
        or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            for value in horizons
        )
    ):
        raise FastPaperShadowMissedOpportunityError(
            "runtime action-policy horizons are invalid"
        )

    horizon_labels: dict[int, dict[tuple[object, ...], object]] = {}
    dataset_fingerprints: dict[str, str] = {}
    if skips:
        identities = tuple(
            evidence.feature_record.decision_identity
            for evidence in skips
        )
        if len(set(identities)) != len(identities):
            raise FastPaperShadowMissedOpportunityError(
                "missed-opportunity SKIP feature identities are duplicated"
            )

        for horizon in horizons:
            try:
                dataset = (
                    load_future_path_training_labels_for_identities_from_sqlite(
                        manifest.observer_database_path,
                        future_path_label_version=label_version,
                        horizon_ms=horizon,
                        decision_identities=identities,
                    )
                )
            except Exception as exc:
                raise FastPaperShadowMissedOpportunityError(
                    "missed-opportunity FL4 future-path load failed closed"
                ) from exc
            _sha256(
                "future-path logical fingerprint",
                dataset.logical_fingerprint_sha256,
            )
            dataset_fingerprints[str(horizon)] = (
                dataset.logical_fingerprint_sha256
            )
            by_identity: dict[tuple[object, ...], object] = {}
            for label in dataset.labels:
                identity = label.decision_identity
                if identity in by_identity:
                    raise FastPaperShadowMissedOpportunityError(
                        "missed-opportunity FL4 identity is duplicated"
                    )
                if (
                    label.horizon_ms != horizon
                    or label.label_version != label_version
                ):
                    raise FastPaperShadowMissedOpportunityError(
                        "missed-opportunity FL4 horizon/version mismatch"
                    )
                by_identity[identity] = label
            if set(by_identity) != set(identities):
                raise FastPaperShadowMissedOpportunityError(
                    "missed-opportunity FL4 identity coverage mismatch"
                )
            horizon_labels[horizon] = by_identity

    per_horizon_accumulator = {
        horizon: {
            "scorable": [],
            "complete_count": 0,
            "incomplete_count": 0,
            "no_trade_count": 0,
            "cost_adjusted_unavailable_count": 0,
            "positive_count": 0,
        }
        for horizon in horizons
    }
    per_skip: list[dict[str, object]] = []
    fully_scorable_values: list[float] = []
    fully_scorable_positive = 0

    for evidence in skips:
        identity = evidence.feature_record.decision_identity
        rows: list[dict[str, object]] = []
        scorable_values: list[tuple[int, float]] = []
        for horizon in horizons:
            label = horizon_labels[horizon][identity]
            row = _score_label(label)
            rows.append(
                {
                    "horizon_ms": horizon,
                    **row,
                }
            )
            accumulator = per_horizon_accumulator[horizon]
            if label.completeness == "complete":
                accumulator["complete_count"] += 1
            else:
                accumulator["incomplete_count"] += 1
            if label.no_trade_events:
                accumulator["no_trade_count"] += 1
            if (
                label.completeness == "complete"
                and not label.no_trade_events
                and label.best_cost_adjusted_return_bps is None
            ):
                accumulator["cost_adjusted_unavailable_count"] += 1
            missed = row["missed_opportunity_bps"]
            if missed is not None:
                assert isinstance(missed, float)
                accumulator["scorable"].append(missed)
                if missed > 0.0:
                    accumulator["positive_count"] += 1
                scorable_values.append((horizon, missed))

        fully_scorable = len(scorable_values) == len(horizons)
        if fully_scorable:
            best_value = max(value for _horizon, value in scorable_values)
            best_horizon = min(
                horizon
                for horizon, value in scorable_values
                if math.isclose(value, best_value, rel_tol=0.0, abs_tol=0.0)
            )
            fully_scorable_values.append(best_value)
            if best_value > 0.0:
                fully_scorable_positive += 1
        else:
            best_value = None
            best_horizon = None

        per_skip.append(
            {
                "source_sequence": evidence.source_sequence,
                "source_event_id": evidence.source_event_id,
                "as_of_unix_ms": evidence.as_of_unix_ms,
                "market_key": evidence.market_key,
                "mint": evidence.feature_record.mint,
                "decision_signature": (
                    evidence.feature_record.decision_signature
                ),
                "decision_ordinal": (
                    evidence.feature_record.decision_ordinal
                ),
                "fully_scorable_across_policy_horizons": fully_scorable,
                "best_missed_opportunity_bps": best_value,
                "best_missed_opportunity_horizon_ms": best_horizon,
                "horizons": rows,
            }
        )

    per_horizon: list[dict[str, object]] = []
    for horizon in horizons:
        accumulator = per_horizon_accumulator[horizon]
        scorable = accumulator["scorable"]
        assert isinstance(scorable, list)
        positive_count = int(accumulator["positive_count"])
        per_horizon.append(
            {
                "horizon_ms": horizon,
                "skip_count": len(skips),
                "complete_label_count": int(
                    accumulator["complete_count"]
                ),
                "incomplete_label_count": int(
                    accumulator["incomplete_count"]
                ),
                "scorable_count": len(scorable),
                "no_trade_event_count": int(
                    accumulator["no_trade_count"]
                ),
                "cost_adjusted_unavailable_count": int(
                    accumulator["cost_adjusted_unavailable_count"]
                ),
                "positive_missed_opportunity_count": positive_count,
                "positive_missed_opportunity_rate": (
                    None
                    if not scorable
                    else positive_count / len(scorable)
                ),
                "missed_opportunity_bps": _summary(scorable),
            }
        )

    fully_scorable_count = len(fully_scorable_values)
    if not skips:
        evidence_state = "NO_SKIP_DECISIONS"
    elif fully_scorable_count == len(skips):
        evidence_state = "COMPLETE"
    else:
        evidence_state = "PARTIAL"

    material: dict[str, object] = {
        "schema_name": FAST_PAPER_SHADOW_MISSED_OPPORTUNITY_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_MISSED_OPPORTUNITY_SCHEMA_VERSION,
        "release_source_sha": expected_sha,
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": (
            manifest.champion_fingerprint_sha256
        ),
        "strategy_family": manifest.strategy_family,
        "strategy_version": manifest.strategy_version,
        "action_policy_version": manifest.action_policy.version,
        "binding_fingerprint_sha256": (
            binding.binding_fingerprint_sha256
        ),
        "window_since_unix_ms": since,
        "window_until_unix_ms": until,
        "window_duration_ms": until - since,
        "sample_proof_fingerprint_sha256": sample[
            "report_fingerprint_sha256"
        ],
        "sample_policy_version": sample["policy_version"],
        "future_path_label_version": label_version,
        "policy_horizons_ms": list(horizons),
        "decision_count": len(decisions),
        "skip_decision_count": len(skips),
        "non_skip_decision_count": len(decisions) - len(skips),
        "future_path_dataset_fingerprints_sha256": (
            dataset_fingerprints
        ),
        "missed_opportunity_evidence_state": evidence_state,
        "fully_scorable_skip_count": fully_scorable_count,
        "partially_or_unscorable_skip_count": (
            len(skips) - fully_scorable_count
        ),
        "positive_missed_opportunity_count": fully_scorable_positive,
        "positive_missed_opportunity_rate": (
            None
            if not fully_scorable_values
            else fully_scorable_positive / len(fully_scorable_values)
        ),
        "best_missed_opportunity_bps": _summary(
            fully_scorable_values
        ),
        "per_horizon": per_horizon,
        "per_skip_decision": per_skip,
        "promotion_authority": "NOT_GRANTED",
        "production_paper_cutover": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return _finalize(material)


def _score_label(label: object) -> dict[str, object]:
    completeness = getattr(label, "completeness", None)
    no_trade = getattr(label, "no_trade_events", None)
    best = getattr(label, "best_cost_adjusted_return_bps", None)
    if completeness not in {"complete", "incomplete"}:
        raise FastPaperShadowMissedOpportunityError(
            "missed-opportunity FL4 completeness is invalid"
        )
    if type(no_trade) is not bool:
        raise FastPaperShadowMissedOpportunityError(
            "missed-opportunity FL4 no-trade flag is invalid"
        )
    if completeness != "complete":
        return {
            "status": "INCOMPLETE_FUTURE_PATH",
            "best_cost_adjusted_return_bps": None,
            "missed_opportunity_bps": None,
        }
    if no_trade:
        return {
            "status": "SCORABLE_NO_TRADE_EVENTS",
            "best_cost_adjusted_return_bps": None,
            "missed_opportunity_bps": 0.0,
        }
    if best is None:
        return {
            "status": "COST_ADJUSTED_ECONOMICS_UNAVAILABLE",
            "best_cost_adjusted_return_bps": None,
            "missed_opportunity_bps": None,
        }
    value = _finite("best_cost_adjusted_return_bps", best)
    return {
        "status": "SCORABLE",
        "best_cost_adjusted_return_bps": value,
        "missed_opportunity_bps": max(0.0, value),
    }


def _read_window_decisions(
    evidence_directory: str | Path,
    *,
    manifest: object,
    since_unix_ms: int,
    until_unix_ms: int,
) -> tuple[object, ...]:
    root = _directory(evidence_directory, "decision evidence")
    selected: list[object] = []
    seen_sequences: set[int] = set()
    seen_events: set[str] = set()
    seen_fingerprints: set[str] = set()

    for path in sorted(root.glob("shadow-*.json")):
        if path.is_symlink() or not path.is_file():
            raise FastPaperShadowMissedOpportunityError(
                "missed-opportunity decision evidence path is unsafe"
            )
        match = _EVIDENCE_NAME_RE.fullmatch(path.name)
        if match is None:
            raise FastPaperShadowMissedOpportunityError(
                "missed-opportunity decision evidence filename is incompatible"
            )
        try:
            evidence = read_fast_paper_shadow_decision_evidence(path)
            validate_fast_paper_shadow_decision_evidence(evidence)
        except Exception as exc:
            raise FastPaperShadowMissedOpportunityError(
                "missed-opportunity decision evidence authentication failed"
            ) from exc

        if int(match.group("sequence")) != evidence.source_sequence:
            raise FastPaperShadowMissedOpportunityError(
                "missed-opportunity decision filename/source sequence mismatch"
            )
        if (
            evidence.release_source_sha != manifest.release_source_sha
            or evidence.manifest_fingerprint_sha256
            != manifest.manifest_fingerprint_sha256
            or evidence.champion_version != manifest.champion_version
            or evidence.champion_fingerprint_sha256
            != manifest.champion_fingerprint_sha256
            or evidence.action_policy_version != manifest.action_policy.version
        ):
            raise FastPaperShadowMissedOpportunityError(
                "missed-opportunity decision runtime identity mismatch"
            )
        if evidence.source_sequence in seen_sequences:
            raise FastPaperShadowMissedOpportunityError(
                "missed-opportunity source sequence is duplicated"
            )
        if evidence.source_event_id in seen_events:
            raise FastPaperShadowMissedOpportunityError(
                "missed-opportunity source event is duplicated"
            )
        if evidence.evidence_fingerprint_sha256 in seen_fingerprints:
            raise FastPaperShadowMissedOpportunityError(
                "missed-opportunity evidence fingerprint is duplicated"
            )
        seen_sequences.add(evidence.source_sequence)
        seen_events.add(evidence.source_event_id)
        seen_fingerprints.add(evidence.evidence_fingerprint_sha256)

        if since_unix_ms <= evidence.as_of_unix_ms < until_unix_ms:
            selected.append(evidence)

    selected.sort(key=lambda value: value.source_sequence)
    return tuple(selected)


def _read_sample_proof(path: str | Path) -> dict[str, object]:
    document = _canonical_document(Path(path), "FL11.1 sample proof")
    if frozenset(document) != _SAMPLE_REPORT_KEYS:
        raise FastPaperShadowMissedOpportunityError(
            "FL11.1 sample proof has unknown or missing fields"
        )
    fingerprint = document.get("report_fingerprint_sha256")
    _sha256("sample proof fingerprint", fingerprint)
    material = dict(document)
    material.pop("report_fingerprint_sha256", None)
    if fingerprint != hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest():
        raise FastPaperShadowMissedOpportunityError(
            "FL11.1 sample proof fingerprint mismatch"
        )
    if (
        document.get("schema_name")
        != FAST_PAPER_SHADOW_SAMPLE_PROOF_SCHEMA_NAME
        or document.get("schema_version")
        != FAST_PAPER_SHADOW_SAMPLE_PROOF_SCHEMA_VERSION
    ):
        raise FastPaperShadowMissedOpportunityError(
            "FL11.1 sample proof schema is incompatible"
        )
    if document.get("decision") != "SUFFICIENT_SAMPLE":
        raise FastPaperShadowMissedOpportunityError(
            "FL11.2b requires FL11.1 SUFFICIENT_SAMPLE"
        )
    for name in (
        "promotion_authority",
        "production_paper_cutover",
        "signing_submission_authority",
    ):
        if document.get(name) != "NOT_GRANTED":
            raise FastPaperShadowMissedOpportunityError(
                "FL11.1 sample proof authority boundary is incompatible"
            )
    if document.get("live_authority") != "DISABLED":
        raise FastPaperShadowMissedOpportunityError(
            "FL11.1 sample proof LIVE boundary is incompatible"
        )
    return document


def _require_sample_matches(
    sample: Mapping[str, object],
    *,
    manifest: object,
    binding: object,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> None:
    expected = {
        "release_source_sha": expected_release_sha,
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": manifest.champion_fingerprint_sha256,
        "action_policy_version": manifest.action_policy.version,
        "binding_fingerprint_sha256": binding.binding_fingerprint_sha256,
        "window_since_unix_ms": since_unix_ms,
        "window_until_unix_ms": until_unix_ms,
    }
    for name, value in expected.items():
        if sample.get(name) != value:
            raise FastPaperShadowMissedOpportunityError(
                f"FL11.1 sample proof {name} mismatch"
            )


def canonical_fast_paper_shadow_missed_opportunity(
    document: Mapping[str, object],
) -> str:
    if not isinstance(document, Mapping):
        raise FastPaperShadowMissedOpportunityError(
            "missed-opportunity document must be a mapping"
        )
    try:
        return _canonical(dict(document))
    except (TypeError, ValueError) as exc:
        raise FastPaperShadowMissedOpportunityError(
            "missed-opportunity document is not canonicalizable"
        ) from exc


def _finalize(material: Mapping[str, object]) -> dict[str, object]:
    document = dict(material)
    if "report_fingerprint_sha256" in document:
        raise FastPaperShadowMissedOpportunityError(
            "missed-opportunity material may not predefine fingerprint"
        )
    return {
        **document,
        "report_fingerprint_sha256": hashlib.sha256(
            _canonical(document).encode("utf-8")
        ).hexdigest(),
    }


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {
            "mean": None,
            "p50": None,
            "p95": None,
            "min": None,
            "max": None,
        }
    ordered = sorted(_finite("missed-opportunity value", value) for value in values)
    return {
        "mean": math.fsum(ordered) / len(ordered),
        "p50": _nearest_rank(ordered, 50),
        "p95": _nearest_rank(ordered, 95),
        "min": ordered[0],
        "max": ordered[-1],
    }


def _nearest_rank(values: list[float], percentile: int) -> float:
    rank = max(1, math.ceil(percentile * len(values) / 100.0))
    return float(values[min(rank - 1, len(values) - 1)])


def _canonical_document(path: Path, label: str) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise FastPaperShadowMissedOpportunityError(
            f"{label} must be a regular non-symlink file"
        )
    try:
        payload = path.read_text(encoding="utf-8")
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise FastPaperShadowMissedOpportunityError(
            f"{label} is malformed"
        ) from exc
    if not isinstance(document, dict) or payload != _canonical(document):
        raise FastPaperShadowMissedOpportunityError(
            f"{label} must use canonical JSON"
        )
    return document


def _directory(value: str | Path, label: str) -> Path:
    root = Path(value).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise FastPaperShadowMissedOpportunityError(
            f"missed-opportunity {label} directory must be regular and non-symlink"
        )
    return root


def _release_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperShadowMissedOpportunityError(
            "missed-opportunity release SHA is invalid"
        )
    return value


def _window(since: object, until: object) -> tuple[int, int]:
    if (
        isinstance(since, bool)
        or not isinstance(since, int)
        or since < 0
        or isinstance(until, bool)
        or not isinstance(until, int)
        or until <= since
    ):
        raise FastPaperShadowMissedOpportunityError(
            "missed-opportunity window is invalid"
        )
    return since, until


def _sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FastPaperShadowMissedOpportunityError(
            f"{name} must be lowercase SHA-256"
        )
    return value


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FastPaperShadowMissedOpportunityError(
            f"{name} must be positive integer"
        )
    return value


def _finite(name: str, value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise FastPaperShadowMissedOpportunityError(
            f"{name} must be finite"
        )
    return float(value)


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-shadow-missed-opportunity"
    )
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--ledger-database-path", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--decision-evidence-directory", required=True)
    parser.add_argument("--sample-proof-path", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--since-unix-ms", type=int, required=True)
    parser.add_argument("--until-unix-ms", type=int, required=True)
    parser.add_argument("--future-path-label-version", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = collect_fast_paper_shadow_missed_opportunity(
            manifest_path=args.manifest_path,
            ledger_database_path=args.ledger_database_path,
            run_id=args.run_id,
            decision_evidence_directory=args.decision_evidence_directory,
            sample_proof_path=args.sample_proof_path,
            expected_release_sha=args.expected_release_sha,
            since_unix_ms=args.since_unix_ms,
            until_unix_ms=args.until_unix_ms,
            future_path_label_version=args.future_path_label_version,
        )
    except (FastPaperShadowMissedOpportunityError, ValueError) as exc:
        print(
            canonical_fast_paper_shadow_missed_opportunity(
                {
                    "schema_name": (
                        "shreks.fast_paper_shadow_missed_opportunity_failure"
                    ),
                    "schema_version": (
                        FAST_PAPER_SHADOW_MISSED_OPPORTUNITY_SCHEMA_VERSION
                    ),
                    "state": "FAILED",
                    "error_type": type(exc).__name__,
                    "promotion_authority": "NOT_GRANTED",
                    "production_paper_cutover": "NOT_GRANTED",
                    "signing_submission_authority": "NOT_GRANTED",
                    "live_authority": "DISABLED",
                }
            ),
            end="",
            file=sys.stderr,
        )
        return 1
    print(
        canonical_fast_paper_shadow_missed_opportunity(result),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
