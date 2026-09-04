from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

from shreks_brain.fast_campaign import (
    FastCampaignActionConstraints,
    FastCampaignContinuousActionPolicy,
    FastCampaignReduceExecutionCost,
)
from shreks_brain.fast_campaign_paper import FastCampaignPaperEntryAuthority
from shreks_brain.fast_policy_proof import (
    FastPolicySuperiorityPolicy,
    decode_fast_policy_superiority_policy,
    encode_fast_policy_superiority_policy,
)
from shreks_brain.paper import create_paper_ledger

from .artifact import read_fast_deterministic_campaign_artifact
from .invocation import read_fast_deterministic_campaign_invocation_seal
from .learned import (
    FastLearnedCampaignRow,
    build_fast_learned_campaign_identity,
    run_fast_learned_chronological_campaign,
)
from .paper_evidence import FastDeterministicCampaignPaperEvidence
from .proof_artifact import (
    FastPolicyComparisonArtifact,
    read_fast_policy_comparison_artifact,
    write_fast_policy_comparison_artifact,
)
from .request import decode_fast_deterministic_campaign_request


FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_NAME = (
    "shreks.fast_learned_comparison_request"
)
FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_VERSION = 1

_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "request",
        "request_fingerprint_sha256",
    }
)
_REQUEST_KEYS = frozenset(
    {
        "baseline_invocation_path",
        "champion_path",
        "decision_binary_path",
        "decision_binary_sha256",
        "proof_destination_path",
        "paper_run_id",
        "candidate_version",
        "strategy_family",
        "strategy_version",
        "assessment_version",
        "action_policy",
        "rows",
        "superiority_policy",
    }
)
_ROW_KEYS = frozenset(
    {
        "source_event_id",
        "flat_constraints",
        "open_constraints",
        "entry_authority",
    }
)
_CONSTRAINT_KEYS = frozenset(
    {
        "max_exposure_fraction_hex",
        "buy_economically_allowed",
        "expected_future_exit_cost_bps_hex",
        "reduce_execution_costs",
        "sell_executable",
        "sell_now_cost_bps_hex",
        "force_sell",
    }
)
_REDUCE_KEYS = frozenset(
    {
        "target_exposure_fraction_hex",
        "execution_cost_bps_hex",
    }
)
_ENTRY_KEYS = frozenset(
    {
        "mint",
        "quote_mint",
        "intended_base_quantity_hex",
        "decision_executable_entry_price_quote_hex",
        "maximum_acceptable_entry_price_quote_hex",
        "expected_entry_variable_cost_bps",
        "expected_entry_fixed_cost_quote_hex",
    }
)
_ACTION_POLICY_KEYS = frozenset(
    {
        "version",
        "horizons_ms",
        "entry_exposure_candidates_hex",
        "reduce_target_exposure_candidates_hex",
        "adverse_excursion_weight_hex",
        "reversal_penalty_bps_hex",
        "route_unavailability_penalty_bps_hex",
        "horizon_disagreement_weight_hex",
        "minimum_buy_value_bps_hex",
        "minimum_hold_value_bps_hex",
        "missing_forecast_open_action",
    }
)


@dataclass(frozen=True, slots=True)
class FastLearnedComparisonRowInput:
    source_event_id: str
    flat_constraints: FastCampaignActionConstraints
    open_constraints: FastCampaignActionConstraints
    entry_authority: FastCampaignPaperEntryAuthority | None

    def __post_init__(self) -> None:
        _require_non_empty_string("source_event_id", self.source_event_id)
        if type(self.flat_constraints) is not FastCampaignActionConstraints:
            raise ValueError(
                "flat_constraints must be exact FastCampaignActionConstraints"
            )
        if type(self.open_constraints) is not FastCampaignActionConstraints:
            raise ValueError(
                "open_constraints must be exact FastCampaignActionConstraints"
            )
        if (
            self.entry_authority is not None
            and type(self.entry_authority) is not FastCampaignPaperEntryAuthority
        ):
            raise ValueError(
                "entry_authority must be exact FastCampaignPaperEntryAuthority or None"
            )


@dataclass(frozen=True, slots=True)
class FastLearnedComparisonRequest:
    schema_name: str
    schema_version: int
    baseline_invocation_path: str
    champion_path: str
    decision_binary_path: str
    decision_binary_sha256: str
    proof_destination_path: str
    paper_run_id: str
    candidate_version: str
    strategy_family: str
    strategy_version: str
    assessment_version: str
    action_policy: FastCampaignContinuousActionPolicy
    rows: tuple[FastLearnedComparisonRowInput, ...]
    superiority_policy: FastPolicySuperiorityPolicy
    request_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_NAME:
            raise ValueError(
                "unsupported learned comparison request schema_name"
            )
        if self.schema_version != FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_VERSION:
            raise ValueError(
                "unsupported learned comparison request schema_version"
            )
        for name in (
            "baseline_invocation_path",
            "champion_path",
            "decision_binary_path",
            "proof_destination_path",
            "paper_run_id",
            "candidate_version",
            "strategy_family",
            "strategy_version",
            "assessment_version",
        ):
            _require_non_empty_string(name, getattr(self, name))
        _require_sha256(
            "decision_binary_sha256",
            self.decision_binary_sha256,
        )
        _require_sha256(
            "request_fingerprint_sha256",
            self.request_fingerprint_sha256,
        )
        if type(self.action_policy) is not FastCampaignContinuousActionPolicy:
            raise ValueError(
                "action_policy must be exact FastCampaignContinuousActionPolicy"
            )
        if (
            not isinstance(self.rows, tuple)
            or not self.rows
            or not all(
                type(value) is FastLearnedComparisonRowInput
                for value in self.rows
            )
        ):
            raise ValueError(
                "rows must be a non-empty tuple of exact FastLearnedComparisonRowInput values"
            )
        identities = tuple(value.source_event_id for value in self.rows)
        if len(identities) != len(set(identities)):
            raise ValueError(
                "learned comparison request source_event_id values must be unique"
            )
        if type(self.superiority_policy) is not FastPolicySuperiorityPolicy:
            raise ValueError(
                "superiority_policy must be exact FastPolicySuperiorityPolicy"
            )


def build_fast_learned_comparison_request(
    *,
    baseline_invocation_path: str,
    champion_path: str,
    decision_binary_path: str,
    decision_binary_sha256: str,
    proof_destination_path: str,
    paper_run_id: str,
    candidate_version: str,
    strategy_family: str,
    strategy_version: str,
    assessment_version: str,
    action_policy: FastCampaignContinuousActionPolicy,
    rows: tuple[FastLearnedComparisonRowInput, ...],
    superiority_policy: FastPolicySuperiorityPolicy,
) -> FastLearnedComparisonRequest:
    values = {
        "baseline_invocation_path": baseline_invocation_path,
        "champion_path": champion_path,
        "decision_binary_path": decision_binary_path,
        "decision_binary_sha256": decision_binary_sha256,
        "proof_destination_path": proof_destination_path,
        "paper_run_id": paper_run_id,
        "candidate_version": candidate_version,
        "strategy_family": strategy_family,
        "strategy_version": strategy_version,
        "assessment_version": assessment_version,
        "action_policy": action_policy,
        "rows": rows,
        "superiority_policy": superiority_policy,
    }
    material = _request_material(values)
    return FastLearnedComparisonRequest(
        schema_name=FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_NAME,
        schema_version=FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_VERSION,
        **values,
        request_fingerprint_sha256=_sha256_canonical(material),
    )


def encode_fast_learned_comparison_request(
    request: FastLearnedComparisonRequest,
) -> str:
    if type(request) is not FastLearnedComparisonRequest:
        raise ValueError(
            "request must be exact FastLearnedComparisonRequest"
        )
    values = {
        name: getattr(request, name)
        for name in _REQUEST_KEYS
    }
    material = _request_material(values)
    expected = _sha256_canonical(material)
    if request.request_fingerprint_sha256 != expected:
        raise ValueError(
            "learned comparison request fingerprint mismatch"
        )
    return _canonical(
        {
            **material,
            "request_fingerprint_sha256": (
                request.request_fingerprint_sha256
            ),
        }
    )


def decode_fast_learned_comparison_request(
    payload: str,
) -> FastLearnedComparisonRequest:
    if not isinstance(payload, str) or not payload:
        raise ValueError(
            "learned comparison request payload must be non-empty text"
        )
    try:
        document = json.loads(
            payload,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            "learned comparison request is malformed JSON"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError(
            "learned comparison request must be a JSON object"
        )
    if payload != _canonical(document):
        raise ValueError(
            "learned comparison request must use canonical JSON"
        )
    if frozenset(document) != _TOP_KEYS:
        raise ValueError(
            "learned comparison request has unknown or missing top-level fields"
        )
    if document["schema_name"] != FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_NAME:
        raise ValueError(
            "unsupported learned comparison request schema_name"
        )
    if (
        document["schema_version"]
        != FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_VERSION
    ):
        raise ValueError(
            "unsupported learned comparison request schema_version"
        )
    raw = document["request"]
    if not isinstance(raw, dict) or frozenset(raw) != _REQUEST_KEYS:
        raise ValueError(
            "learned comparison request body has unknown or missing fields"
        )

    raw_rows = raw["rows"]
    if not isinstance(raw_rows, list):
        raise ValueError(
            "learned comparison request rows must be a JSON array"
        )
    try:
        request = FastLearnedComparisonRequest(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            baseline_invocation_path=raw["baseline_invocation_path"],
            champion_path=raw["champion_path"],
            decision_binary_path=raw["decision_binary_path"],
            decision_binary_sha256=raw["decision_binary_sha256"],
            proof_destination_path=raw["proof_destination_path"],
            paper_run_id=raw["paper_run_id"],
            candidate_version=raw["candidate_version"],
            strategy_family=raw["strategy_family"],
            strategy_version=raw["strategy_version"],
            assessment_version=raw["assessment_version"],
            action_policy=_decode_action_policy(raw["action_policy"]),
            rows=tuple(_decode_row(value) for value in raw_rows),
            superiority_policy=decode_fast_policy_superiority_policy(
                _canonical(raw["superiority_policy"])
            ),
            request_fingerprint_sha256=document[
                "request_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"learned comparison request content is incompatible: {exc}"
        ) from exc

    material = {
        "schema_name": document["schema_name"],
        "schema_version": document["schema_version"],
        "request": raw,
    }
    if (
        request.request_fingerprint_sha256
        != _sha256_canonical(material)
    ):
        raise ValueError(
            "learned comparison request fingerprint mismatch"
        )
    return request


def run_fast_learned_comparison_request_file(
    request_path: str | Path,
) -> FastPolicyComparisonArtifact:
    source = Path(request_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(
            "learned comparison request path must identify an existing file"
        )
    request_payload = source.read_text(encoding="utf-8")
    request = decode_fast_learned_comparison_request(request_payload)
    base = source.parent

    invocation_path = _resolve_path(
        base,
        request.baseline_invocation_path,
    )
    champion_path = _source_file(
        base,
        request.champion_path,
        "champion_path",
    )
    decision_binary_path = _source_file(
        base,
        request.decision_binary_path,
        "decision_binary_path",
    )
    proof_destination = _resolve_path(
        base,
        request.proof_destination_path,
    )

    invocation = read_fast_deterministic_campaign_invocation_seal(
        invocation_path
    )
    if proof_destination.parent != invocation.path.parent.resolve():
        raise ValueError(
            "learned comparison proof destination must be a sibling of the baseline invocation"
        )

    baseline_request = decode_fast_deterministic_campaign_request(
        invocation.request_payload
    )
    campaign_path = (
        invocation.path.parent
        / invocation.manifest.campaign_directory_name
    )
    campaign = read_fast_deterministic_campaign_artifact(campaign_path)
    if (
        campaign.manifest.artifact_fingerprint_sha256
        != invocation.manifest.campaign_artifact_fingerprint_sha256
    ):
        raise ValueError(
            "baseline invocation/campaign artifact fingerprint mismatch"
        )

    _authenticate_decision_binary(
        decision_binary_path,
        request.decision_binary_sha256,
    )
    champion_sha256 = _sealed_champion_sha256(invocation)
    _authenticate_file(
        champion_path,
        champion_sha256,
        label="champion",
    )

    learned_rows = _bind_learned_rows(
        campaign.comparison_bundle.rows,
        request.rows,
    )

    identity = build_fast_learned_campaign_identity(
        champion_path=champion_path,
        policy=request.action_policy,
        paper_run_id=request.paper_run_id,
        candidate_version=request.candidate_version,
        strategy_family=request.strategy_family,
        strategy_version=request.strategy_version,
        assessment_version=request.assessment_version,
    )
    starting_ledger = create_paper_ledger(
        baseline_request.starting_cash_usd,
        baseline_request.starting_ledger_as_of_unix_ms,
    )
    result = run_fast_learned_chronological_campaign(
        decision_binary_path=decision_binary_path,
        champion_path=champion_path,
        identity=identity,
        policy=request.action_policy,
        rows=learned_rows,
        starting_ledger=starting_ledger,
        fill_policy=baseline_request.fill_policy,
        risk_policy=baseline_request.risk_policy,
        position_policy=baseline_request.position_policy,
        evaluation_policy=baseline_request.evaluation_policy,
    )

    _authenticate_decision_binary(
        decision_binary_path,
        request.decision_binary_sha256,
    )
    _authenticate_file(
        champion_path,
        champion_sha256,
        label="champion",
    )
    if source.read_text(encoding="utf-8") != request_payload:
        raise ValueError(
            "learned comparison request file changed during execution"
        )

    learned_run = result.run_evidence
    if (
        learned_run.event_population_fingerprint_sha256
        != campaign.manifest.event_population_fingerprint_sha256
    ):
        raise ValueError(
            "learned comparison event population fingerprint does not match baseline population"
        )

    verified_invocation = (
        read_fast_deterministic_campaign_invocation_seal(
            invocation_path
        )
    )
    if verified_invocation.manifest != invocation.manifest:
        raise ValueError(
            "baseline invocation changed during learned comparison execution"
        )

    write_fast_policy_comparison_artifact(
        baseline_invocation_path=invocation.path,
        learned_run=learned_run,
        superiority_policy=request.superiority_policy,
        destination=proof_destination,
    )
    return read_fast_policy_comparison_artifact(proof_destination)


def _bind_learned_rows(
    baseline_rows: tuple[object, ...],
    requested_rows: tuple[FastLearnedComparisonRowInput, ...],
) -> tuple[FastLearnedCampaignRow, ...]:
    if len(baseline_rows) != len(requested_rows):
        raise ValueError(
            "learned comparison source-event population length mismatch"
        )
    values = []
    for index, (baseline, requested) in enumerate(
        zip(baseline_rows, requested_rows)
    ):
        record = baseline.record
        expected_source_event_id = (
            f"{record.decision_signature}:{record.decision_ordinal}"
        )
        if requested.source_event_id != expected_source_event_id:
            raise ValueError(
                "learned comparison source_event population mismatch "
                f"at row {index}"
            )
        _validate_entry_authority(
            requested.entry_authority,
            record=record,
            source_event_id=expected_source_event_id,
        )
        evidence = FastDeterministicCampaignPaperEvidence(
            source_event_id=expected_source_event_id,
            state_version=baseline.state_version,
            evaluated_at_unix_ms=baseline.evaluated_at_unix_ms,
            quote=baseline.quote,
            risk_context=None,
            entry_authority=requested.entry_authority,
            market_regime=baseline.market_regime,
            risk_environment=baseline.risk_environment,
            entry_quote=baseline.entry_quote,
            exit_quote=baseline.exit_quote,
        )
        values.append(
            FastLearnedCampaignRow(
                record=record,
                flat_constraints=requested.flat_constraints,
                open_constraints=requested.open_constraints,
                paper_evidence=evidence,
            )
        )
    return tuple(values)


def _validate_entry_authority(
    authority: FastCampaignPaperEntryAuthority | None,
    *,
    record: object,
    source_event_id: str,
) -> None:
    if authority is None:
        return
    if authority.mint != record.mint:
        raise ValueError(
            f"learned entry authority mint mismatch for {source_event_id}"
        )
    if authority.quote_mint != record.quote_mint:
        raise ValueError(
            f"learned entry authority quote mint mismatch for {source_event_id}"
        )
    if (
        authority.decision_executable_entry_price_quote
        != record.decision_executable_entry_price_quote
    ):
        raise ValueError(
            "learned entry authority decision price provenance mismatch "
            f"for {source_event_id}"
        )


def _request_material(values: dict[str, object]) -> dict[str, object]:
    if frozenset(values) != _REQUEST_KEYS:
        raise ValueError(
            "learned comparison request material field set is invalid"
        )
    rows = values["rows"]
    if not isinstance(rows, tuple):
        raise ValueError("learned comparison request rows must be tuple")
    action_policy = values["action_policy"]
    if type(action_policy) is not FastCampaignContinuousActionPolicy:
        raise ValueError(
            "action_policy must be exact FastCampaignContinuousActionPolicy"
        )
    superiority = values["superiority_policy"]
    if type(superiority) is not FastPolicySuperiorityPolicy:
        raise ValueError(
            "superiority_policy must be exact FastPolicySuperiorityPolicy"
        )
    return {
        "schema_name": FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_NAME,
        "schema_version": FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_VERSION,
        "request": {
            "baseline_invocation_path": values[
                "baseline_invocation_path"
            ],
            "champion_path": values["champion_path"],
            "decision_binary_path": values["decision_binary_path"],
            "decision_binary_sha256": values[
                "decision_binary_sha256"
            ],
            "proof_destination_path": values[
                "proof_destination_path"
            ],
            "paper_run_id": values["paper_run_id"],
            "candidate_version": values["candidate_version"],
            "strategy_family": values["strategy_family"],
            "strategy_version": values["strategy_version"],
            "assessment_version": values["assessment_version"],
            "action_policy": _encode_action_policy(action_policy),
            "rows": [_encode_row(value) for value in rows],
            "superiority_policy": json.loads(
                encode_fast_policy_superiority_policy(superiority)
            ),
        },
    }


def _encode_row(
    value: FastLearnedComparisonRowInput,
) -> dict[str, object]:
    if type(value) is not FastLearnedComparisonRowInput:
        raise ValueError(
            "learned comparison rows must contain exact row inputs"
        )
    return {
        "source_event_id": value.source_event_id,
        "flat_constraints": _encode_constraints(
            value.flat_constraints
        ),
        "open_constraints": _encode_constraints(
            value.open_constraints
        ),
        "entry_authority": (
            None
            if value.entry_authority is None
            else _encode_entry_authority(value.entry_authority)
        ),
    }


def _decode_row(value: object) -> FastLearnedComparisonRowInput:
    if not isinstance(value, dict) or frozenset(value) != _ROW_KEYS:
        raise ValueError(
            "learned comparison row has unknown or missing fields"
        )
    authority = value["entry_authority"]
    return FastLearnedComparisonRowInput(
        source_event_id=value["source_event_id"],
        flat_constraints=_decode_constraints(
            value["flat_constraints"]
        ),
        open_constraints=_decode_constraints(
            value["open_constraints"]
        ),
        entry_authority=(
            None
            if authority is None
            else _decode_entry_authority(authority)
        ),
    )


def _encode_action_policy(
    value: FastCampaignContinuousActionPolicy,
) -> dict[str, object]:
    return {
        "version": value.version,
        "horizons_ms": list(value.horizons_ms),
        "entry_exposure_candidates_hex": [
            _float_hex(item)
            for item in value.entry_exposure_candidates
        ],
        "reduce_target_exposure_candidates_hex": [
            _float_hex(item)
            for item in value.reduce_target_exposure_candidates
        ],
        "adverse_excursion_weight_hex": _float_hex(
            value.adverse_excursion_weight
        ),
        "reversal_penalty_bps_hex": _float_hex(
            value.reversal_penalty_bps
        ),
        "route_unavailability_penalty_bps_hex": _float_hex(
            value.route_unavailability_penalty_bps
        ),
        "horizon_disagreement_weight_hex": _float_hex(
            value.horizon_disagreement_weight
        ),
        "minimum_buy_value_bps_hex": _float_hex(
            value.minimum_buy_value_bps
        ),
        "minimum_hold_value_bps_hex": _float_hex(
            value.minimum_hold_value_bps
        ),
        "missing_forecast_open_action": (
            value.missing_forecast_open_action
        ),
    }


def _decode_action_policy(
    value: object,
) -> FastCampaignContinuousActionPolicy:
    if (
        not isinstance(value, dict)
        or frozenset(value) != _ACTION_POLICY_KEYS
    ):
        raise ValueError(
            "learned comparison action policy has unknown or missing fields"
        )
    horizons = value["horizons_ms"]
    entries = value["entry_exposure_candidates_hex"]
    reductions = value["reduce_target_exposure_candidates_hex"]
    if not isinstance(horizons, list):
        raise ValueError("action policy horizons_ms must be array")
    if not isinstance(entries, list) or not isinstance(reductions, list):
        raise ValueError(
            "action policy exposure candidates must be arrays"
        )
    return FastCampaignContinuousActionPolicy(
        version=value["version"],
        horizons_ms=tuple(horizons),
        entry_exposure_candidates=tuple(
            _decode_float_hex(item) for item in entries
        ),
        reduce_target_exposure_candidates=tuple(
            _decode_float_hex(item) for item in reductions
        ),
        adverse_excursion_weight=_decode_float_hex(
            value["adverse_excursion_weight_hex"]
        ),
        reversal_penalty_bps=_decode_float_hex(
            value["reversal_penalty_bps_hex"]
        ),
        route_unavailability_penalty_bps=_decode_float_hex(
            value["route_unavailability_penalty_bps_hex"]
        ),
        horizon_disagreement_weight=_decode_float_hex(
            value["horizon_disagreement_weight_hex"]
        ),
        minimum_buy_value_bps=_decode_float_hex(
            value["minimum_buy_value_bps_hex"]
        ),
        minimum_hold_value_bps=_decode_float_hex(
            value["minimum_hold_value_bps_hex"]
        ),
        missing_forecast_open_action=value[
            "missing_forecast_open_action"
        ],
    )


def _encode_constraints(
    value: FastCampaignActionConstraints,
) -> dict[str, object]:
    if type(value) is not FastCampaignActionConstraints:
        raise ValueError(
            "constraint must be exact FastCampaignActionConstraints"
        )
    return {
        "max_exposure_fraction_hex": _float_hex(
            value.max_exposure_fraction
        ),
        "buy_economically_allowed": value.buy_economically_allowed,
        "expected_future_exit_cost_bps_hex": _float_hex(
            value.expected_future_exit_cost_bps
        ),
        "reduce_execution_costs": [
            {
                "target_exposure_fraction_hex": _float_hex(
                    item.target_exposure_fraction
                ),
                "execution_cost_bps_hex": _float_hex(
                    item.execution_cost_bps
                ),
            }
            for item in value.reduce_execution_costs
        ],
        "sell_executable": value.sell_executable,
        "sell_now_cost_bps_hex": _float_hex(
            value.sell_now_cost_bps
        ),
        "force_sell": value.force_sell,
    }


def _decode_constraints(value: object) -> FastCampaignActionConstraints:
    if (
        not isinstance(value, dict)
        or frozenset(value) != _CONSTRAINT_KEYS
    ):
        raise ValueError(
            "learned comparison constraints have unknown or missing fields"
        )
    raw_reduce = value["reduce_execution_costs"]
    if not isinstance(raw_reduce, list):
        raise ValueError(
            "reduce_execution_costs must be a JSON array"
        )
    reduce_values = []
    for item in raw_reduce:
        if (
            not isinstance(item, dict)
            or frozenset(item) != _REDUCE_KEYS
        ):
            raise ValueError(
                "reduce execution cost has unknown or missing fields"
            )
        reduce_values.append(
            FastCampaignReduceExecutionCost(
                target_exposure_fraction=_decode_float_hex(
                    item["target_exposure_fraction_hex"]
                ),
                execution_cost_bps=_decode_float_hex(
                    item["execution_cost_bps_hex"]
                ),
            )
        )
    return FastCampaignActionConstraints(
        max_exposure_fraction=_decode_float_hex(
            value["max_exposure_fraction_hex"]
        ),
        buy_economically_allowed=value[
            "buy_economically_allowed"
        ],
        expected_future_exit_cost_bps=_decode_float_hex(
            value["expected_future_exit_cost_bps_hex"]
        ),
        reduce_execution_costs=tuple(reduce_values),
        sell_executable=value["sell_executable"],
        sell_now_cost_bps=_decode_float_hex(
            value["sell_now_cost_bps_hex"]
        ),
        force_sell=value["force_sell"],
    )


def _encode_entry_authority(
    value: FastCampaignPaperEntryAuthority,
) -> dict[str, object]:
    return {
        "mint": value.mint,
        "quote_mint": value.quote_mint,
        "intended_base_quantity_hex": _float_hex(
            value.intended_base_quantity
        ),
        "decision_executable_entry_price_quote_hex": _float_hex(
            value.decision_executable_entry_price_quote
        ),
        "maximum_acceptable_entry_price_quote_hex": _float_hex(
            value.maximum_acceptable_entry_price_quote
        ),
        "expected_entry_variable_cost_bps": (
            value.expected_entry_variable_cost_bps
        ),
        "expected_entry_fixed_cost_quote_hex": _float_hex(
            value.expected_entry_fixed_cost_quote
        ),
    }


def _decode_entry_authority(
    value: object,
) -> FastCampaignPaperEntryAuthority:
    if not isinstance(value, dict) or frozenset(value) != _ENTRY_KEYS:
        raise ValueError(
            "learned comparison entry authority has unknown or missing fields"
        )
    return FastCampaignPaperEntryAuthority(
        mint=value["mint"],
        quote_mint=value["quote_mint"],
        intended_base_quantity=_decode_float_hex(
            value["intended_base_quantity_hex"]
        ),
        decision_executable_entry_price_quote=_decode_float_hex(
            value["decision_executable_entry_price_quote_hex"]
        ),
        maximum_acceptable_entry_price_quote=_decode_float_hex(
            value["maximum_acceptable_entry_price_quote_hex"]
        ),
        expected_entry_variable_cost_bps=value[
            "expected_entry_variable_cost_bps"
        ],
        expected_entry_fixed_cost_quote=_decode_float_hex(
            value["expected_entry_fixed_cost_quote_hex"]
        ),
    )


def _sealed_champion_sha256(invocation: object) -> str:
    matches = tuple(
        value
        for value in invocation.sources
        if value.label == "champion_path"
    )
    if len(matches) != 1:
        raise ValueError(
            "baseline invocation must contain exactly one champion source"
        )
    components = matches[0].components
    if (
        len(components) != 1
        or components[0].role != "file"
    ):
        raise ValueError(
            "baseline invocation champion source must contain one file component"
        )
    claimed = components[0].sha256
    _require_sha256("sealed champion sha256", claimed)
    return claimed


def _authenticate_decision_binary(
    path: Path,
    expected_sha256: str,
) -> None:
    _authenticate_file(
        path,
        expected_sha256,
        label="decision binary",
    )


def _authenticate_file(
    path: Path,
    expected_sha256: str,
    *,
    label: str,
) -> None:
    actual = _sha256_file(path)
    if actual != expected_sha256:
        raise ValueError(
            f"{label} SHA-256 fingerprint mismatch"
        )


def _source_file(base: Path, value: str, name: str) -> Path:
    path = _resolve_path(base, value)
    if not path.is_file():
        raise ValueError(f"{name} must resolve to an existing file")
    return path


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    before = path.stat()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    after = path.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError(
            "authenticated source changed while fingerprinting"
        )
    return digest.hexdigest()


def _float_hex(value: float) -> str:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError("request float must be finite")
    return float(value).hex()


def _decode_float_hex(value: object) -> float:
    if not isinstance(value, str):
        raise ValueError("request float encoding must be string")
    try:
        decoded = float.fromhex(value)
    except ValueError as exc:
        raise ValueError("request float encoding is malformed") from exc
    if not math.isfinite(decoded):
        raise ValueError("request float must be finite")
    return decoded


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _reject_json_constant(value: str) -> None:
    raise ValueError(
        f"non-finite JSON number is forbidden: {value}"
    )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(
            character not in "0123456789abcdef"
            for character in value
        )
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
