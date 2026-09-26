from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from shreks_brain.fast_campaign_paper import (
    FastCampaignPaperDecisionEvidence,
    FastCampaignPaperEntryAuthority,
    FastCampaignPaperQuoteEvidence,
)
from shreks_brain.fast_paper import FastPaperPositionActionPolicy
from shreks_brain.paper import PaperFillPolicy, PaperQuoteState
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import RiskContext, RiskPolicy

from .codec import verify_fast_paper_runtime_bindings
from .models import FastPaperRuntimeManifest
from .shadow import (
    FastPaperShadowDecisionEvidence,
    FastPaperShadowQuoteEvidence,
)


FAST_PAPER_SHADOW_EXECUTION_POLICY_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_execution_policy"
)
FAST_PAPER_SHADOW_EXECUTION_POLICY_SCHEMA_VERSION = 1

_POLICY_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "manifest_fingerprint_sha256",
        "risk_policy",
        "fill_policy",
        "position_action_policy",
        "policy_fingerprint_sha256",
    }
)
_POLICY_TYPES = (
    RiskPolicy,
    PaperFillPolicy,
    FastPaperPositionActionPolicy,
)
_POLICY_TYPE_BY_NAME = {
    value.__name__: value for value in _POLICY_TYPES
}
_POLICY_NAME_BY_TYPE = {
    value: value.__name__ for value in _POLICY_TYPES
}
_REL_TOL = 1e-12
_ABS_TOL = 1e-15


@dataclass(frozen=True, slots=True)
class FastPaperShadowExecutionPolicy:
    schema_name: str
    schema_version: int
    manifest_fingerprint_sha256: str
    risk_policy: RiskPolicy
    fill_policy: PaperFillPolicy
    position_action_policy: FastPaperPositionActionPolicy
    policy_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_SHADOW_EXECUTION_POLICY_SCHEMA_NAME:
            raise ValueError(
                "shadow execution policy schema_name is incompatible"
            )
        if (
            type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_SHADOW_EXECUTION_POLICY_SCHEMA_VERSION
        ):
            raise ValueError(
                "shadow execution policy schema_version is incompatible"
            )
        _require_sha256(
            "manifest_fingerprint_sha256",
            self.manifest_fingerprint_sha256,
        )
        if type(self.risk_policy) is not RiskPolicy:
            raise ValueError(
                "risk_policy must be exact RiskPolicy"
            )
        if type(self.fill_policy) is not PaperFillPolicy:
            raise ValueError(
                "fill_policy must be exact PaperFillPolicy"
            )
        if (
            type(self.position_action_policy)
            is not FastPaperPositionActionPolicy
        ):
            raise ValueError(
                "position_action_policy must be exact FastPaperPositionActionPolicy"
            )
        _require_sha256(
            "policy_fingerprint_sha256",
            self.policy_fingerprint_sha256,
        )
        if (
            _execution_policy_fingerprint(self)
            != self.policy_fingerprint_sha256
        ):
            raise ValueError(
                "shadow execution policy fingerprint mismatch"
            )


@dataclass(frozen=True, slots=True)
class FastPaperShadowQuoteUsdEvidence:
    quote_mint: str
    observed_at_unix_ms: int
    quote_to_usd_rate: float
    source_version: str
    source_fingerprint_sha256: str

    def __post_init__(self) -> None:
        _require_text("quote_mint", self.quote_mint)
        _require_non_negative_int(
            "observed_at_unix_ms",
            self.observed_at_unix_ms,
        )
        _require_positive_finite(
            "quote_to_usd_rate",
            self.quote_to_usd_rate,
        )
        object.__setattr__(
            self,
            "quote_to_usd_rate",
            float(self.quote_to_usd_rate),
        )
        _require_text("source_version", self.source_version)
        _require_sha256(
            "source_fingerprint_sha256",
            self.source_fingerprint_sha256,
        )


@dataclass(frozen=True, slots=True)
class FastPaperShadowExecutionInput:
    decision_evidence: FastPaperShadowDecisionEvidence
    entry_authority: FastCampaignPaperEntryAuthority | None
    risk_context: RiskContext | None
    market_regime: MarketRegime | None
    quote_usd_evidence: FastPaperShadowQuoteUsdEvidence | None

    def __post_init__(self) -> None:
        if (
            type(self.decision_evidence)
            is not FastPaperShadowDecisionEvidence
        ):
            raise ValueError(
                "decision_evidence must be exact FastPaperShadowDecisionEvidence"
            )
        if (
            self.entry_authority is not None
            and type(self.entry_authority)
            is not FastCampaignPaperEntryAuthority
        ):
            raise ValueError(
                "entry_authority must be exact FastCampaignPaperEntryAuthority or None"
            )
        if (
            self.risk_context is not None
            and type(self.risk_context) is not RiskContext
        ):
            raise ValueError(
                "risk_context must be exact RiskContext or None"
            )
        if (
            self.market_regime is not None
            and type(self.market_regime) is not MarketRegime
        ):
            raise ValueError(
                "market_regime must be exact MarketRegime or None"
            )
        if (
            self.quote_usd_evidence is not None
            and type(self.quote_usd_evidence)
            is not FastPaperShadowQuoteUsdEvidence
        ):
            raise ValueError(
                "quote_usd_evidence must be exact FastPaperShadowQuoteUsdEvidence or None"
            )

        evidence = self.decision_evidence
        action = evidence.decision.action
        posture = evidence.position.kind

        if self.quote_usd_evidence is not None:
            usd = self.quote_usd_evidence
            if usd.quote_mint != evidence.entry_quote.quote_mint:
                raise ValueError(
                    "shadow execution USD quote mint does not match decision evidence"
                )
            if usd.observed_at_unix_ms > evidence.evaluated_at_unix_ms:
                raise ValueError(
                    "future USD evidence cannot authorize shadow execution"
                )

        if action == "BUY":
            if posture != "FLAT":
                raise ValueError(
                    "BUY shadow execution requires FLAT learned posture"
                )
            if (
                self.entry_authority is None
                or self.risk_context is None
                or self.market_regime is None
                or self.quote_usd_evidence is None
            ):
                raise ValueError(
                    "BUY shadow execution requires explicit entry authority, risk, regime, and USD evidence"
                )
            if evidence.entry_quote.state != "EXECUTABLE":
                raise ValueError(
                    "BUY shadow execution requires executable ENTRY quote evidence"
                )
            if (
                self.risk_context.as_of_unix_ms
                != evidence.evaluated_at_unix_ms
            ):
                raise ValueError(
                    "BUY risk context timestamp must equal shadow execution evaluation time"
                )
            _validate_entry_authority(
                self.entry_authority,
                evidence,
            )
            return

        if action == "SKIP":
            if posture != "FLAT":
                raise ValueError(
                    "SKIP shadow execution requires FLAT learned posture"
                )
            if any(
                value is not None
                for value in (
                    self.entry_authority,
                    self.risk_context,
                    self.market_regime,
                    self.quote_usd_evidence,
                )
            ):
                raise ValueError(
                    "SKIP shadow execution cannot carry execution authority or USD evidence"
                )
            return

        if action not in {"HOLD", "REDUCE", "SELL"}:
            raise ValueError(
                "shadow execution action is unsupported"
            )
        if posture != "OPEN":
            raise ValueError(
                f"{action} shadow execution requires OPEN learned posture"
            )
        if any(
            value is not None
            for value in (
                self.entry_authority,
                self.risk_context,
                self.market_regime,
            )
        ):
            raise ValueError(
                "non-BUY shadow execution cannot carry BUY entry/risk/regime authority"
            )
        if self.quote_usd_evidence is None:
            raise ValueError(
                f"{action} shadow execution requires explicit USD evidence"
            )
        if action == "REDUCE":
            _reduction_quote_for_selected_target(evidence)


def build_fast_paper_shadow_execution_policy(
    manifest: FastPaperRuntimeManifest,
    *,
    risk_policy: RiskPolicy,
    fill_policy: PaperFillPolicy,
    position_action_policy: FastPaperPositionActionPolicy,
) -> FastPaperShadowExecutionPolicy:
    _require_manifest_and_policy_compatibility(
        manifest,
        risk_policy=risk_policy,
        fill_policy=fill_policy,
        position_action_policy=position_action_policy,
    )
    values = {
        "schema_name": FAST_PAPER_SHADOW_EXECUTION_POLICY_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_EXECUTION_POLICY_SCHEMA_VERSION,
        "manifest_fingerprint_sha256": (
            manifest.manifest_fingerprint_sha256
        ),
        "risk_policy": risk_policy,
        "fill_policy": fill_policy,
        "position_action_policy": position_action_policy,
    }
    fingerprint = hashlib.sha256(
        _canonical_json(
            _execution_policy_document_values(values)
        )
    ).hexdigest()
    return FastPaperShadowExecutionPolicy(
        **values,
        policy_fingerprint_sha256=fingerprint,
    )


def write_fast_paper_shadow_execution_policy(
    policy: FastPaperShadowExecutionPolicy,
    destination: str | Path,
) -> None:
    if type(policy) is not FastPaperShadowExecutionPolicy:
        raise ValueError(
            "policy must be exact FastPaperShadowExecutionPolicy"
        )
    if (
        _execution_policy_fingerprint(policy)
        != policy.policy_fingerprint_sha256
    ):
        raise ValueError(
            "shadow execution policy fingerprint mismatch"
        )

    path = Path(destination).expanduser()
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "shadow execution policy destination already exists"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        _canonical_json(_execution_policy_document(policy))
        + b"\n"
    )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    published = False
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        os.link(temporary, path, follow_symlinks=False)
        published = True
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
        temporary.unlink()
        _fsync_directory(path.parent)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        if published:
            path.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        raise


def read_fast_paper_shadow_execution_policy(
    manifest: FastPaperRuntimeManifest,
    source: str | Path,
) -> FastPaperShadowExecutionPolicy:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    path = Path(source).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "shadow execution policy source must be a regular non-symlink file"
        )
    payload = path.read_bytes()
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        raise ValueError(
            "shadow execution policy must have exactly one trailing newline"
        )
    raw = payload[:-1]
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            "shadow execution policy is malformed JSON"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError(
            "shadow execution policy must be a JSON object"
        )
    if frozenset(document) != _POLICY_KEYS:
        raise ValueError(
            "shadow execution policy has unknown or missing fields"
        )
    if _canonical_json(document) != raw:
        raise ValueError(
            "shadow execution policy must use canonical JSON"
        )

    try:
        claimed = document["policy_fingerprint_sha256"]
        _require_sha256(
            "policy_fingerprint_sha256",
            claimed,
        )
        risk_policy = _decode_policy_value(
            document["risk_policy"],
            RiskPolicy,
        )
        fill_policy = _decode_policy_value(
            document["fill_policy"],
            PaperFillPolicy,
        )
        position_action_policy = _decode_policy_value(
            document["position_action_policy"],
            FastPaperPositionActionPolicy,
        )
        policy = build_fast_paper_shadow_execution_policy(
            manifest,
            risk_policy=risk_policy,
            fill_policy=fill_policy,
            position_action_policy=position_action_policy,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"shadow execution policy content is incompatible: {exc}"
        ) from exc

    if document["schema_name"] != policy.schema_name:
        raise ValueError(
            "shadow execution policy schema_name is incompatible"
        )
    if document["schema_version"] != policy.schema_version:
        raise ValueError(
            "shadow execution policy schema_version is incompatible"
        )
    if (
        document["manifest_fingerprint_sha256"]
        != policy.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "shadow execution policy manifest fingerprint mismatch"
        )
    if claimed != policy.policy_fingerprint_sha256:
        raise ValueError(
            "shadow execution policy fingerprint mismatch"
        )
    if _execution_policy_document(policy) != document:
        raise ValueError(
            "shadow execution policy payload is not canonical for decoded values"
        )
    return policy


def materialize_fast_paper_shadow_execution_evidence(
    manifest: FastPaperRuntimeManifest,
    execution_policy: FastPaperShadowExecutionPolicy,
    source: FastPaperShadowExecutionInput,
) -> FastCampaignPaperDecisionEvidence:
    if type(source) is not FastPaperShadowExecutionInput:
        raise ValueError(
            "source must be exact FastPaperShadowExecutionInput"
        )
    _require_execution_policy_binding(
        manifest,
        execution_policy,
    )
    evidence = source.decision_evidence
    _require_decision_binding(
        manifest,
        evidence,
    )

    action = evidence.decision.action
    if action == "SKIP":
        quote = None
    elif action == "BUY":
        assert source.quote_usd_evidence is not None
        quote = _paper_quote(
            evidence.entry_quote,
            source.quote_usd_evidence.quote_to_usd_rate,
        )
    elif action == "REDUCE":
        assert source.quote_usd_evidence is not None
        quote = _paper_quote(
            _reduction_quote_for_selected_target(evidence),
            source.quote_usd_evidence.quote_to_usd_rate,
        )
    elif action in {"HOLD", "SELL"}:
        assert source.quote_usd_evidence is not None
        quote = _paper_quote(
            evidence.exit_quote,
            source.quote_usd_evidence.quote_to_usd_rate,
        )
    else:
        raise ValueError(
            "shadow execution action is unsupported"
        )

    return FastCampaignPaperDecisionEvidence(
        source_event_id=evidence.source_event_id,
        state_version=manifest.state_version,
        evaluated_at_unix_ms=evidence.evaluated_at_unix_ms,
        quote=quote,
        risk_context=source.risk_context if action == "BUY" else None,
        entry_authority=(
            source.entry_authority if action == "BUY" else None
        ),
        market_regime=(
            source.market_regime if action == "BUY" else None
        ),
    )


def _require_manifest_and_policy_compatibility(
    manifest: FastPaperRuntimeManifest,
    *,
    risk_policy: RiskPolicy,
    fill_policy: PaperFillPolicy,
    position_action_policy: FastPaperPositionActionPolicy,
) -> None:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(risk_policy) is not RiskPolicy:
        raise ValueError(
            "risk_policy must be exact RiskPolicy"
        )
    if type(fill_policy) is not PaperFillPolicy:
        raise ValueError(
            "fill_policy must be exact PaperFillPolicy"
        )
    if (
        type(position_action_policy)
        is not FastPaperPositionActionPolicy
    ):
        raise ValueError(
            "position_action_policy must be exact FastPaperPositionActionPolicy"
        )

    verify_fast_paper_runtime_bindings(manifest)

    if risk_policy.version != manifest.risk_policy_version:
        raise ValueError(
            "shadow execution risk policy version does not match runtime manifest"
        )
    if fill_policy.version != manifest.fill_policy_version:
        raise ValueError(
            "shadow execution fill policy version does not match runtime manifest"
        )
    if (
        position_action_policy.version
        != manifest.position_action_policy_version
    ):
        raise ValueError(
            "shadow execution position-action policy version does not match runtime manifest"
        )
    if (
        risk_policy.required_decision_policy_version
        != manifest.assessment_version
    ):
        raise ValueError(
            "shadow execution risk decision/assessment compatibility mismatch"
        )
    if (
        risk_policy.required_feature_schema_version
        != manifest.state_version
    ):
        raise ValueError(
            "shadow execution risk state compatibility mismatch"
        )


def _require_execution_policy_binding(
    manifest: FastPaperRuntimeManifest,
    policy: FastPaperShadowExecutionPolicy,
) -> None:
    if type(policy) is not FastPaperShadowExecutionPolicy:
        raise ValueError(
            "execution_policy must be exact FastPaperShadowExecutionPolicy"
        )
    _require_manifest_and_policy_compatibility(
        manifest,
        risk_policy=policy.risk_policy,
        fill_policy=policy.fill_policy,
        position_action_policy=policy.position_action_policy,
    )
    if (
        policy.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "shadow execution policy manifest fingerprint mismatch"
        )
    if (
        _execution_policy_fingerprint(policy)
        != policy.policy_fingerprint_sha256
    ):
        raise ValueError(
            "shadow execution policy fingerprint mismatch"
        )


def _require_decision_binding(
    manifest: FastPaperRuntimeManifest,
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    if type(evidence) is not FastPaperShadowDecisionEvidence:
        raise ValueError(
            "decision evidence must be exact FastPaperShadowDecisionEvidence"
        )
    expected = (
        manifest.release_source_sha,
        manifest.manifest_fingerprint_sha256,
        manifest.champion_version,
        manifest.champion_fingerprint_sha256,
        manifest.action_policy.version,
    )
    actual = (
        evidence.release_source_sha,
        evidence.manifest_fingerprint_sha256,
        evidence.champion_version,
        evidence.champion_fingerprint_sha256,
        evidence.action_policy_version,
    )
    if actual != expected:
        raise ValueError(
            "shadow execution decision evidence does not match runtime manifest"
        )


def _validate_entry_authority(
    authority: FastCampaignPaperEntryAuthority,
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    quote = evidence.entry_quote
    if authority.mint != quote.mint:
        raise ValueError(
            "BUY entry authority mint does not match shadow entry quote"
        )
    if authority.quote_mint != quote.quote_mint:
        raise ValueError(
            "BUY entry authority quote mint does not match shadow entry quote"
        )
    reference = quote.reference_price_quote
    if reference is None or not math.isclose(
        authority.decision_executable_entry_price_quote,
        reference,
        rel_tol=_REL_TOL,
        abs_tol=_ABS_TOL,
    ):
        raise ValueError(
            "BUY entry authority decision price provenance mismatch"
        )


def _reduction_quote_for_selected_target(
    evidence: FastPaperShadowDecisionEvidence,
) -> FastPaperShadowQuoteEvidence:
    target = evidence.decision.target_exposure_fraction
    matches = tuple(
        item.quote
        for item in evidence.reduction_quotes
        if item.target_exposure_fraction == target
    )
    if len(matches) != 1:
        raise ValueError(
            "REDUCE shadow execution requires exactly one target-matched reduction quote"
        )
    return matches[0]


def _paper_quote(
    value: FastPaperShadowQuoteEvidence,
    quote_to_usd_rate: float,
) -> FastCampaignPaperQuoteEvidence:
    if type(value) is not FastPaperShadowQuoteEvidence:
        raise ValueError(
            "shadow quote must be exact FastPaperShadowQuoteEvidence"
        )
    _require_positive_finite(
        "quote_to_usd_rate",
        quote_to_usd_rate,
    )
    try:
        state = PaperQuoteState(value.state)
    except ValueError as exc:
        raise ValueError(
            "shadow quote state cannot be adapted to PAPER quote state"
        ) from exc
    return FastCampaignPaperQuoteEvidence(
        provider=value.provider,
        mint=value.mint,
        quote_mint=value.quote_mint,
        observed_at_unix_ms=value.observed_at_unix_ms,
        state=state,
        reference_price_quote=value.reference_price_quote,
        execution_price_quote=value.execution_price_quote,
        quoted_base_quantity=value.quoted_base_quantity,
        available_base_quantity=value.available_base_quantity,
        quote_to_usd_rate=float(quote_to_usd_rate),
    )


def _execution_policy_fingerprint(
    policy: FastPaperShadowExecutionPolicy,
) -> str:
    return hashlib.sha256(
        _canonical_json(
            _execution_policy_document_values(
                {
                    "schema_name": policy.schema_name,
                    "schema_version": policy.schema_version,
                    "manifest_fingerprint_sha256": (
                        policy.manifest_fingerprint_sha256
                    ),
                    "risk_policy": policy.risk_policy,
                    "fill_policy": policy.fill_policy,
                    "position_action_policy": (
                        policy.position_action_policy
                    ),
                }
            )
        )
    ).hexdigest()


def _execution_policy_document(
    policy: FastPaperShadowExecutionPolicy,
) -> dict[str, object]:
    document = _execution_policy_document_values(
        {
            "schema_name": policy.schema_name,
            "schema_version": policy.schema_version,
            "manifest_fingerprint_sha256": (
                policy.manifest_fingerprint_sha256
            ),
            "risk_policy": policy.risk_policy,
            "fill_policy": policy.fill_policy,
            "position_action_policy": (
                policy.position_action_policy
            ),
        }
    )
    document["policy_fingerprint_sha256"] = (
        policy.policy_fingerprint_sha256
    )
    return document


def _execution_policy_document_values(
    values: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_name": values["schema_name"],
        "schema_version": values["schema_version"],
        "manifest_fingerprint_sha256": (
            values["manifest_fingerprint_sha256"]
        ),
        "risk_policy": _encode_policy_value(
            values["risk_policy"]
        ),
        "fill_policy": _encode_policy_value(
            values["fill_policy"]
        ),
        "position_action_policy": _encode_policy_value(
            values["position_action_policy"]
        ),
    }


def _encode_policy_value(value: object) -> object:
    value_type = type(value)
    name = _POLICY_NAME_BY_TYPE.get(value_type)
    if name is None or not is_dataclass(value):
        raise ValueError(
            "shadow execution policy contains unsupported value type"
        )
    return {
        "$type": name,
        "fields": {
            field.name: _encode_scalar(
                getattr(value, field.name)
            )
            for field in fields(value)
        },
    }


def _encode_scalar(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                "shadow execution policy floats must be finite"
            )
        return {"$float": value.hex()}
    raise ValueError(
        "shadow execution policy field type is unsupported"
    )


def _decode_policy_value(
    value: object,
    expected_type: type,
):
    if not isinstance(value, dict) or set(value) != {
        "$type",
        "fields",
    }:
        raise ValueError(
            "shadow execution policy typed value is malformed"
        )
    type_name = value["$type"]
    expected_name = _POLICY_NAME_BY_TYPE.get(expected_type)
    if type_name != expected_name:
        raise ValueError(
            "shadow execution policy typed value has wrong type"
        )
    raw_fields = value["fields"]
    if not isinstance(raw_fields, dict):
        raise ValueError(
            "shadow execution policy typed fields are malformed"
        )
    expected_fields = {
        field.name for field in fields(expected_type)
    }
    if set(raw_fields) != expected_fields:
        raise ValueError(
            "shadow execution policy typed fields have unknown or missing fields"
        )
    decoded = {
        name: _decode_scalar(raw_fields[name])
        for name in expected_fields
    }
    try:
        result = expected_type(**decoded)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "shadow execution policy typed value is invalid"
        ) from exc
    if type(result) is not expected_type:
        raise ValueError(
            "shadow execution policy typed value did not decode exactly"
        )
    return result


def _decode_scalar(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float) or isinstance(value, list):
        raise ValueError(
            "raw JSON float/array is not allowed in shadow execution policy"
        )
    if not isinstance(value, dict) or set(value) != {"$float"}:
        raise ValueError(
            "shadow execution policy scalar tag is malformed"
        )
    encoded = value["$float"]
    if not isinstance(encoded, str):
        raise ValueError(
            "shadow execution policy float tag is malformed"
        )
    try:
        result = float.fromhex(encoded)
    except ValueError as exc:
        raise ValueError(
            "shadow execution policy float value is malformed"
        ) from exc
    if not math.isfinite(result) or result.hex() != encoded:
        raise ValueError(
            "shadow execution policy float value is non-canonical"
        )
    return result


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "shadow execution policy cannot be encoded canonically"
        ) from exc


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(
                "shadow execution policy JSON contains duplicate keys"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(
        f"shadow execution policy JSON contains invalid constant {value}"
    )


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{name} must be a non-empty string"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative integer"
        )


def _require_positive_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise ValueError(
            f"{name} must be positive and finite"
        )


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
        raise ValueError(
            f"{name} must be lowercase SHA-256 hex"
        )
