from __future__ import annotations

import hashlib
import json

from .models import FastPolicySuperiorityPolicy


FAST_POLICY_SUPERIORITY_POLICY_SCHEMA_NAME = (
    "shreks.fast_policy_superiority_policy"
)
FAST_POLICY_SUPERIORITY_POLICY_SCHEMA_VERSION = 1

_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "version",
        "required_baseline_versions",
        "min_material_decision_count",
        "min_distinct_market_count",
        "min_evaluation_span_ms",
        "min_trade_count",
        "min_distinct_traded_mint_count",
        "min_net_expectancy_pct",
        "min_profit_factor",
        "max_drawdown_pct",
        "max_cost_burden_pct",
        "max_single_winner_share_of_positive_pnl",
        "min_baseline_expectancy_advantage_pct",
        "policy_fingerprint_sha256",
    }
)


def encode_fast_policy_superiority_policy(
    policy: FastPolicySuperiorityPolicy,
) -> str:
    if type(policy) is not FastPolicySuperiorityPolicy:
        raise ValueError(
            "policy must be exact FastPolicySuperiorityPolicy"
        )
    material = _material(policy)
    document = {
        **material,
        "policy_fingerprint_sha256": _sha256_canonical(material),
    }
    return _canonical(document)


def decode_fast_policy_superiority_policy(
    payload: str,
) -> FastPolicySuperiorityPolicy:
    if not isinstance(payload, str) or not payload:
        raise ValueError(
            "Fast policy superiority policy payload must be non-empty"
        )
    try:
        document = json.loads(
            payload,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            "malformed Fast policy superiority policy JSON"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError(
            "Fast policy superiority policy document must be an object"
        )
    if frozenset(document) != _FIELDS:
        raise ValueError(
            "Fast policy superiority policy has unknown or missing fields"
        )
    if payload != _canonical(document):
        raise ValueError(
            "Fast policy superiority policy JSON must be canonical"
        )
    if (
        document["schema_name"]
        != FAST_POLICY_SUPERIORITY_POLICY_SCHEMA_NAME
    ):
        raise ValueError(
            "unsupported Fast policy superiority policy schema_name"
        )
    if (
        document["schema_version"]
        != FAST_POLICY_SUPERIORITY_POLICY_SCHEMA_VERSION
    ):
        raise ValueError(
            "unsupported Fast policy superiority policy schema_version"
        )

    raw_versions = document["required_baseline_versions"]
    if not isinstance(raw_versions, list):
        raise ValueError(
            "required_baseline_versions must be a JSON array"
        )
    try:
        policy = FastPolicySuperiorityPolicy(
            version=document["version"],
            required_baseline_versions=tuple(raw_versions),
            min_material_decision_count=document[
                "min_material_decision_count"
            ],
            min_distinct_market_count=document[
                "min_distinct_market_count"
            ],
            min_evaluation_span_ms=document[
                "min_evaluation_span_ms"
            ],
            min_trade_count=document["min_trade_count"],
            min_distinct_traded_mint_count=document[
                "min_distinct_traded_mint_count"
            ],
            min_net_expectancy_pct=document[
                "min_net_expectancy_pct"
            ],
            min_profit_factor=document["min_profit_factor"],
            max_drawdown_pct=document["max_drawdown_pct"],
            max_cost_burden_pct=document["max_cost_burden_pct"],
            max_single_winner_share_of_positive_pnl=document[
                "max_single_winner_share_of_positive_pnl"
            ],
            min_baseline_expectancy_advantage_pct=document[
                "min_baseline_expectancy_advantage_pct"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Fast policy superiority policy content is incompatible"
        ) from exc

    claimed = document["policy_fingerprint_sha256"]
    _require_sha256("policy_fingerprint_sha256", claimed)
    expected = _sha256_canonical(_material(policy))
    if claimed != expected:
        raise ValueError(
            "Fast policy superiority policy fingerprint mismatch"
        )
    return policy


def fast_policy_superiority_policy_fingerprint_sha256(
    policy: FastPolicySuperiorityPolicy,
) -> str:
    if type(policy) is not FastPolicySuperiorityPolicy:
        raise ValueError(
            "policy must be exact FastPolicySuperiorityPolicy"
        )
    return _sha256_canonical(_material(policy))


def _material(
    policy: FastPolicySuperiorityPolicy,
) -> dict[str, object]:
    return {
        "schema_name": FAST_POLICY_SUPERIORITY_POLICY_SCHEMA_NAME,
        "schema_version": FAST_POLICY_SUPERIORITY_POLICY_SCHEMA_VERSION,
        "version": policy.version,
        "required_baseline_versions": list(
            policy.required_baseline_versions
        ),
        "min_material_decision_count": (
            policy.min_material_decision_count
        ),
        "min_distinct_market_count": policy.min_distinct_market_count,
        "min_evaluation_span_ms": policy.min_evaluation_span_ms,
        "min_trade_count": policy.min_trade_count,
        "min_distinct_traded_mint_count": (
            policy.min_distinct_traded_mint_count
        ),
        "min_net_expectancy_pct": policy.min_net_expectancy_pct,
        "min_profit_factor": policy.min_profit_factor,
        "max_drawdown_pct": policy.max_drawdown_pct,
        "max_cost_burden_pct": policy.max_cost_burden_pct,
        "max_single_winner_share_of_positive_pnl": (
            policy.max_single_winner_share_of_positive_pnl
        ),
        "min_baseline_expectancy_advantage_pct": (
            policy.min_baseline_expectancy_advantage_pct
        ),
    }


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
