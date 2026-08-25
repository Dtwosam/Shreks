from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from shreks_brain.paper import PaperQuote
from shreks_brain.paper_loop import (
    FreshLaunchSetupInput,
    PaperCycleInput,
    PaperEntryCandidate,
    PaperExitObservation,
    PaperLoopState,
)
from shreks_brain.regime import RecentStrategyPerformance
from shreks_brain.scoring import score_candidate
from shreks_brain.setups import assess_fresh_launch

from .assembler import (
    ObserverFreshLaunchPolicyBundle,
    assemble_observer_paper_cycle,
)
from .models import ObserverPaperRiskEnvironment


OBSERVER_PAPER_CAMPAIGN_CYCLE_AUDIT_SCHEMA_VERSION = (
    "g1b-observer-paper-campaign-cycle-audit-v1"
)


class ObserverCampaignCoordinatorError(ValueError):
    """Raised when a multi-token paper campaign cannot proceed without guessing."""


@dataclass(frozen=True, slots=True)
class ObserverPaperCampaignSelectionPolicy:
    recent_lookback_ms: int
    max_entry_candidates: int

    def __post_init__(self) -> None:
        _require_positive_int("recent_lookback_ms", self.recent_lookback_ms)
        _require_positive_int("max_entry_candidates", self.max_entry_candidates)


@dataclass(frozen=True, slots=True)
class ObserverCampaignCandidate:
    candidate_id: int
    mint: str
    latest_market_observed_at_unix_ms: int

    def __post_init__(self) -> None:
        _require_positive_int("candidate_id", self.candidate_id)
        _require_non_empty_string("mint", self.mint)
        _require_non_negative_int(
            "latest_market_observed_at_unix_ms",
            self.latest_market_observed_at_unix_ms,
        )


@dataclass(frozen=True, slots=True)
class ObserverPaperCampaignCycleAudit:
    schema_version: str
    as_of_unix_ms: int
    selected_candidate_ids: tuple[int, ...]
    selected_mints: tuple[str, ...]
    ranked_entry_mints: tuple[str, ...]
    component_paper_cycle_fingerprints: tuple[str, ...]
    aggregate_cycle_fingerprint: str

    def __post_init__(self) -> None:
        if self.schema_version != OBSERVER_PAPER_CAMPAIGN_CYCLE_AUDIT_SCHEMA_VERSION:
            raise ValueError("unsupported observer paper campaign cycle audit schema")
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if not isinstance(self.selected_candidate_ids, tuple) or not all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0
            for value in self.selected_candidate_ids
        ):
            raise ValueError("selected_candidate_ids must be a tuple of positive integers")
        _require_unique_non_empty_strings("selected_mints", self.selected_mints)
        _require_unique_non_empty_strings("ranked_entry_mints", self.ranked_entry_mints)
        if not set(self.ranked_entry_mints).issubset(set(self.selected_mints)):
            raise ValueError("ranked_entry_mints must be selected mints")
        if not isinstance(self.component_paper_cycle_fingerprints, tuple):
            raise ValueError("component_paper_cycle_fingerprints must be a tuple")
        if len(self.component_paper_cycle_fingerprints) != len(self.selected_mints):
            raise ValueError("component fingerprint count must match selected mints")
        for value in self.component_paper_cycle_fingerprints:
            _require_sha256("component_paper_cycle_fingerprint", value)
        _require_sha256("aggregate_cycle_fingerprint", self.aggregate_cycle_fingerprint)


_REQUIRED_COLUMNS = {
    "token_candidates": frozenset(
        {
            "id",
            "mint",
            "discovered_at_unix_ms",
        }
    ),
    "market_snapshots": frozenset(
        {
            "id",
            "candidate_id",
            "observed_at_unix_ms",
        }
    ),
}


class ObserverCampaignCandidateStore:
    """Read-only point-in-time candidate enumeration for paper coordination."""

    def __init__(self, database_path: str | os.PathLike[str]) -> None:
        try:
            path = Path(database_path).expanduser()
            if not path.exists() or not path.is_file():
                raise ObserverCampaignCoordinatorError(
                    "observer campaign database not found"
                )
            self._database_path = path.resolve(strict=True)
        except ObserverCampaignCoordinatorError:
            raise
        except (TypeError, ValueError, OSError) as error:
            raise ObserverCampaignCoordinatorError(
                "invalid observer campaign database path"
            ) from error

        connection = self._connect()
        try:
            self._validate_schema(connection)
        finally:
            connection.close()

    def recent_candidates(
        self,
        *,
        as_of_unix_ms: int,
        policy: ObserverPaperCampaignSelectionPolicy,
    ) -> tuple[ObserverCampaignCandidate, ...]:
        _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)
        if type(policy) is not ObserverPaperCampaignSelectionPolicy:
            raise ObserverCampaignCoordinatorError(
                "policy must be an exact ObserverPaperCampaignSelectionPolicy"
            )
        cutoff = max(0, as_of_unix_ms - policy.recent_lookback_ms)

        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT
                       candidate.id,
                       candidate.mint,
                       MAX(snapshot.observed_at_unix_ms) AS latest_market_observed_at
                    FROM token_candidates AS candidate
                    JOIN market_snapshots AS snapshot
                      ON snapshot.candidate_id = candidate.id
                    WHERE candidate.discovered_at_unix_ms <= ?
                      AND snapshot.observed_at_unix_ms BETWEEN ? AND ?
                    GROUP BY candidate.id, candidate.mint
                    ORDER BY latest_market_observed_at DESC, candidate.id ASC""",
                (as_of_unix_ms, cutoff, as_of_unix_ms),
            ).fetchall()
            candidates = tuple(_candidate_from_row(row) for row in rows)
            _reject_ambiguous_mints(candidates)
            return candidates[: policy.max_entry_candidates]
        except ObserverCampaignCoordinatorError:
            raise
        except sqlite3.Error as error:
            raise ObserverCampaignCoordinatorError(
                f"observer campaign recent-candidate read failed: {error}"
            ) from error
        except (TypeError, ValueError) as error:
            raise ObserverCampaignCoordinatorError(
                f"observer campaign recent-candidate evidence is invalid: {error}"
            ) from error
        finally:
            connection.close()

    def resolve_required_mints(
        self,
        mints: tuple[str, ...],
        *,
        as_of_unix_ms: int,
    ) -> tuple[ObserverCampaignCandidate, ...]:
        if not isinstance(mints, tuple):
            raise ObserverCampaignCoordinatorError("mints must be a tuple")
        for mint in mints:
            _require_non_empty_string("mint", mint)
        _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)

        ordered_mints = tuple(dict.fromkeys(mints))
        connection = self._connect()
        try:
            resolved: list[ObserverCampaignCandidate] = []
            for mint in ordered_mints:
                rows = connection.execute(
                    """SELECT
                           candidate.id,
                           candidate.mint,
                           MAX(snapshot.observed_at_unix_ms) AS latest_market_observed_at
                        FROM token_candidates AS candidate
                        LEFT JOIN market_snapshots AS snapshot
                          ON snapshot.candidate_id = candidate.id
                         AND snapshot.observed_at_unix_ms <= ?
                        WHERE candidate.mint = ?
                          AND candidate.discovered_at_unix_ms <= ?
                        GROUP BY candidate.id, candidate.mint
                        ORDER BY candidate.id ASC""",
                    (as_of_unix_ms, mint, as_of_unix_ms),
                ).fetchall()
                if not rows:
                    raise ObserverCampaignCoordinatorError(
                        f"required observer candidate mint '{mint}' not found at point in time"
                    )
                if len(rows) != 1:
                    raise ObserverCampaignCoordinatorError(
                        f"required observer candidate mint '{mint}' is ambiguous"
                    )
                row = rows[0]
                if row[2] is None:
                    raise ObserverCampaignCoordinatorError(
                        f"required observer candidate mint '{mint}' has no point-in-time market evidence"
                    )
                resolved.append(_candidate_from_row(row))
            return tuple(resolved)
        except ObserverCampaignCoordinatorError:
            raise
        except sqlite3.Error as error:
            raise ObserverCampaignCoordinatorError(
                f"required observer candidate read failed: {error}"
            ) from error
        except (TypeError, ValueError) as error:
            raise ObserverCampaignCoordinatorError(
                f"required observer candidate evidence is invalid: {error}"
            ) from error
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                f"file:{self._database_path}?mode=ro",
                uri=True,
            )
            connection.execute("PRAGMA query_only = ON")
            return connection
        except sqlite3.Error as error:
            raise ObserverCampaignCoordinatorError(
                f"observer campaign database open failed: {error}"
            ) from error

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        try:
            for table, required in _REQUIRED_COLUMNS.items():
                rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
                columns = frozenset(str(row[1]) for row in rows)
                missing = required - columns
                if missing:
                    raise ObserverCampaignCoordinatorError(
                        f"observer campaign database missing {table} columns: "
                        + ", ".join(sorted(missing))
                    )
        except ObserverCampaignCoordinatorError:
            raise
        except sqlite3.Error as error:
            raise ObserverCampaignCoordinatorError(
                f"observer campaign schema validation failed: {error}"
            ) from error


def assemble_observer_paper_campaign_cycle(
    database_path: str | os.PathLike[str],
    state: PaperLoopState,
    as_of_unix_ms: int,
    policy_bundle: ObserverFreshLaunchPolicyBundle,
    environment: ObserverPaperRiskEnvironment,
    selection_policy: ObserverPaperCampaignSelectionPolicy,
    *,
    recent_performance: RecentStrategyPerformance | None = None,
    global_risk_halt: bool,
) -> tuple[PaperCycleInput, ObserverPaperCampaignCycleAudit]:
    if type(state) is not PaperLoopState:
        raise ObserverCampaignCoordinatorError("state must be an exact PaperLoopState")
    _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)
    if type(policy_bundle) is not ObserverFreshLaunchPolicyBundle:
        raise ObserverCampaignCoordinatorError(
            "policy_bundle must be an exact ObserverFreshLaunchPolicyBundle"
        )
    if type(environment) is not ObserverPaperRiskEnvironment:
        raise ObserverCampaignCoordinatorError(
            "environment must be an exact ObserverPaperRiskEnvironment"
        )
    if type(selection_policy) is not ObserverPaperCampaignSelectionPolicy:
        raise ObserverCampaignCoordinatorError(
            "selection_policy must be an exact ObserverPaperCampaignSelectionPolicy"
        )
    if recent_performance is not None and type(recent_performance) is not RecentStrategyPerformance:
        raise ObserverCampaignCoordinatorError(
            "recent_performance must be an exact RecentStrategyPerformance or None"
        )
    if type(global_risk_halt) is not bool:
        raise ObserverCampaignCoordinatorError("global_risk_halt must be a boolean")

    store = ObserverCampaignCandidateStore(database_path)
    required_mints = tuple(
        managed.exit_state.mint for managed in state.managed_positions
    )
    if state.pending_entry is not None:
        required_mints += (state.pending_entry.intent.mint,)

    required = store.resolve_required_mints(
        tuple(dict.fromkeys(required_mints)),
        as_of_unix_ms=as_of_unix_ms,
    )
    recent = store.recent_candidates(
        as_of_unix_ms=as_of_unix_ms,
        policy=selection_policy,
    )
    selected = _merge_selected_candidates(required, recent)

    components: list[tuple[ObserverCampaignCandidate, PaperCycleInput, str]] = []
    for candidate in selected:
        candidate_bundle = replace(
            policy_bundle,
            entry_quote_identity=replace(
                policy_bundle.entry_quote_identity,
                candidate_id=candidate.candidate_id,
                output_mint=candidate.mint,
            ),
        )
        try:
            component_cycle, component_audit = assemble_observer_paper_cycle(
                database_path,
                state,
                as_of_unix_ms,
                candidate_bundle,
                environment,
                recent_performance=recent_performance,
                global_risk_halt=global_risk_halt,
            )
        except ValueError as error:
            raise ObserverCampaignCoordinatorError(
                f"observer candidate {candidate.candidate_id} assembly failed: {error}"
            ) from error
        if component_cycle.as_of_unix_ms != as_of_unix_ms:
            raise ObserverCampaignCoordinatorError(
                "component paper cycle timestamp changed during aggregation"
            )
        if component_audit.candidate_id != candidate.candidate_id or component_audit.mint != candidate.mint:
            raise ObserverCampaignCoordinatorError(
                "component paper cycle attribution changed during aggregation"
            )
        components.append(
            (candidate, component_cycle, component_audit.paper_cycle_fingerprint)
        )

    entries_by_mint: dict[str, PaperEntryCandidate] = {}
    exits_by_id: dict[str, PaperExitObservation] = {}
    quotes_by_mint: dict[str, PaperQuote] = {}
    candidate_ids_by_mint = {value.mint: value.candidate_id for value in selected}

    for candidate, cycle, _ in components:
        if len(cycle.entry_candidates) != 1 or cycle.entry_candidates[0].mint != candidate.mint:
            raise ObserverCampaignCoordinatorError(
                "component paper cycle must contain exactly its attributed entry candidate"
            )
        _insert_unique(entries_by_mint, candidate.mint, cycle.entry_candidates[0], "entry candidate")
        for observation in cycle.exit_observations:
            _insert_unique(exits_by_id, observation.position_id, observation, "exit observation")
        for quote in cycle.quotes:
            _insert_unique(quotes_by_mint, quote.mint, quote, "paper quote")

    ranked_entries = tuple(
        sorted(
            entries_by_mint.values(),
            key=lambda item: _entry_rank_key(item, candidate_ids_by_mint[item.mint]),
        )
    )
    ranked_mints = tuple(item.mint for item in ranked_entries)

    quote_order = ranked_mints + tuple(
        candidate.mint for candidate in selected if candidate.mint not in ranked_mints
    )
    quotes = tuple(quotes_by_mint[mint] for mint in quote_order if mint in quotes_by_mint)
    exits = tuple(exits_by_id[key] for key in sorted(exits_by_id))

    try:
        aggregate = PaperCycleInput(
            as_of_unix_ms=as_of_unix_ms,
            entry_candidates=ranked_entries,
            exit_observations=exits,
            quotes=quotes,
        )
    except ValueError as error:
        raise ObserverCampaignCoordinatorError(
            f"aggregate paper cycle is invalid: {error}"
        ) from error

    component_fingerprints = tuple(value[2] for value in components)
    audit_payload = {
        "schema_version": OBSERVER_PAPER_CAMPAIGN_CYCLE_AUDIT_SCHEMA_VERSION,
        "as_of_unix_ms": as_of_unix_ms,
        "selected_candidate_ids": [value.candidate_id for value in selected],
        "selected_mints": [value.mint for value in selected],
        "ranked_entry_mints": list(ranked_mints),
        "component_paper_cycle_fingerprints": list(component_fingerprints),
    }
    audit = ObserverPaperCampaignCycleAudit(
        schema_version=OBSERVER_PAPER_CAMPAIGN_CYCLE_AUDIT_SCHEMA_VERSION,
        as_of_unix_ms=as_of_unix_ms,
        selected_candidate_ids=tuple(value.candidate_id for value in selected),
        selected_mints=tuple(value.mint for value in selected),
        ranked_entry_mints=ranked_mints,
        component_paper_cycle_fingerprints=component_fingerprints,
        aggregate_cycle_fingerprint=_fingerprint(audit_payload),
    )
    return aggregate, audit


def _merge_selected_candidates(
    required: tuple[ObserverCampaignCandidate, ...],
    recent: tuple[ObserverCampaignCandidate, ...],
) -> tuple[ObserverCampaignCandidate, ...]:
    by_mint: dict[str, ObserverCampaignCandidate] = {}
    ordered: list[ObserverCampaignCandidate] = []
    for candidate in required + recent:
        existing = by_mint.get(candidate.mint)
        if existing is None:
            by_mint[candidate.mint] = candidate
            ordered.append(candidate)
            continue
        if existing.candidate_id != candidate.candidate_id:
            raise ObserverCampaignCoordinatorError(
                f"observer candidate mint '{candidate.mint}' resolved to conflicting identities"
            )
    return tuple(ordered)


def _entry_rank_key(
    candidate: PaperEntryCandidate,
    observer_candidate_id: int,
) -> tuple[int, float, int, str]:
    if type(candidate.setup) is not FreshLaunchSetupInput:
        raise ObserverCampaignCoordinatorError(
            "G1B V1 entry ordering supports Fresh Launch candidates only"
        )
    try:
        setup = assess_fresh_launch(candidate.features, candidate.setup.policy)
        score = score_candidate(
            candidate.features,
            setup,
            candidate.regime,
            candidate.score_policy,
        )
    except (TypeError, ValueError) as error:
        raise ObserverCampaignCoordinatorError(
            f"entry score reconstruction failed for mint '{candidate.mint}': {error}"
        ) from error
    if score.total_score is None:
        return (1, 0.0, observer_candidate_id, candidate.mint)
    return (0, -score.total_score, observer_candidate_id, candidate.mint)


def _insert_unique(mapping: dict[str, object], key: str, value: object, label: str) -> None:
    existing = mapping.get(key)
    if existing is None:
        mapping[key] = value
        return
    if existing != value:
        raise ObserverCampaignCoordinatorError(
            f"conflicting duplicate {label} for '{key}'"
        )


def _candidate_from_row(row: tuple[object, ...]) -> ObserverCampaignCandidate:
    if len(row) != 3:
        raise ObserverCampaignCoordinatorError("observer campaign candidate row is malformed")
    candidate_id, mint, latest_market = row
    try:
        return ObserverCampaignCandidate(
            candidate_id=candidate_id,  # type: ignore[arg-type]
            mint=mint,  # type: ignore[arg-type]
            latest_market_observed_at_unix_ms=latest_market,  # type: ignore[arg-type]
        )
    except ValueError as error:
        raise ObserverCampaignCoordinatorError(str(error)) from error


def _reject_ambiguous_mints(
    candidates: tuple[ObserverCampaignCandidate, ...],
) -> None:
    by_mint: dict[str, int] = {}
    for candidate in candidates:
        existing = by_mint.get(candidate.mint)
        if existing is not None and existing != candidate.candidate_id:
            raise ObserverCampaignCoordinatorError(
                f"recent observer candidate mint '{candidate.mint}' is ambiguous"
            )
        by_mint[candidate.mint] = candidate.candidate_id


def _fingerprint(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ObserverCampaignCoordinatorError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ObserverCampaignCoordinatorError(
            f"{name} must be a non-negative integer"
        )


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ObserverCampaignCoordinatorError(f"{name} must be positive")


def _require_unique_non_empty_strings(name: str, values: object) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{name} must be a tuple")
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError(f"{name} must contain non-empty strings")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates")


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be a 64-character sha256")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{name} must be hexadecimal sha256") from error


from shreks_brain.paper_evaluation import (
    PaperEvaluationEvidenceStore,
    PaperEvaluationLedger,
)
from shreks_brain.paper_loop import (
    PaperCycleResult,
    PaperLoopFinding,
    PaperLoopReasonCode,
    run_paper_cycle,
)
from shreks_brain.paper_validation import (
    AccountingValidationStatus,
    PaperCheckpointError,
    PaperCheckpointRecord,
    load_latest_paper_checkpoint,
    save_paper_checkpoint,
    validate_paper_accounting,
    validate_restart_equivalence,
)
from shreks_brain.registry import RegistryCandidate


class ObserverPaperCampaignCoordinatorRunner:
    """Restart-safe PAPER runner over one aggregate observer campaign cycle."""

    def __init__(
        self,
        observer_database_path: str | os.PathLike[str],
        evidence_path: str | os.PathLike[str],
        candidate: RegistryCandidate,
        paper_run_id: str,
        initial_state: PaperLoopState,
        policy_bundle: ObserverFreshLaunchPolicyBundle,
        risk_environment: ObserverPaperRiskEnvironment,
        selection_policy: ObserverPaperCampaignSelectionPolicy,
        *,
        recent_performance: RecentStrategyPerformance | None = None,
        global_risk_halt: bool,
    ) -> None:
        if type(candidate) is not RegistryCandidate:
            raise ObserverCampaignCoordinatorError(
                "candidate must be an exact RegistryCandidate"
            )
        _require_non_empty_string("paper_run_id", paper_run_id)
        if type(initial_state) is not PaperLoopState:
            raise ObserverCampaignCoordinatorError(
                "initial_state must be an exact PaperLoopState"
            )
        if type(policy_bundle) is not ObserverFreshLaunchPolicyBundle:
            raise ObserverCampaignCoordinatorError(
                "policy_bundle must be an exact ObserverFreshLaunchPolicyBundle"
            )
        if type(risk_environment) is not ObserverPaperRiskEnvironment:
            raise ObserverCampaignCoordinatorError(
                "risk_environment must be an exact ObserverPaperRiskEnvironment"
            )
        if type(selection_policy) is not ObserverPaperCampaignSelectionPolicy:
            raise ObserverCampaignCoordinatorError(
                "selection_policy must be an exact ObserverPaperCampaignSelectionPolicy"
            )
        if recent_performance is not None and type(recent_performance) is not RecentStrategyPerformance:
            raise ObserverCampaignCoordinatorError(
                "recent_performance must be an exact RecentStrategyPerformance or None"
            )
        if type(global_risk_halt) is not bool:
            raise ObserverCampaignCoordinatorError("global_risk_halt must be a boolean")
        if candidate.strategy_version != policy_bundle.fresh_launch_policy.version:
            raise ObserverCampaignCoordinatorError(
                "registry candidate strategy attribution does not match Fresh Launch policy"
            )
        if candidate.feature_schema_version != policy_bundle.score_policy.required_feature_schema_version:
            raise ObserverCampaignCoordinatorError(
                "registry candidate feature attribution does not match bundled score policy"
            )

        try:
            self._observer_database_path = Path(observer_database_path).expanduser().resolve()
            self._evidence_path = Path(evidence_path).expanduser().resolve()
        except (TypeError, ValueError, OSError) as error:
            raise ObserverCampaignCoordinatorError("campaign paths are invalid") from error

        self._candidate = candidate
        self._paper_run_id = paper_run_id
        self._initial_state = initial_state
        self._policy_bundle = policy_bundle
        self._risk_environment = risk_environment
        self._selection_policy = selection_policy
        self._recent_performance = recent_performance
        self._global_risk_halt = global_risk_halt
        self._evidence_store = PaperEvaluationEvidenceStore(self._evidence_path)
        self._require_accounting_not_invalid(initial_state, "initial state")

    def load_state(self) -> PaperLoopState:
        state, _ = self._load_state_and_checkpoint()
        return state

    def run_cycle(
        self,
        as_of_unix_ms: int,
        created_at_unix_ms: int,
    ) -> PaperCycleResult:
        _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)
        _require_non_negative_int("created_at_unix_ms", created_at_unix_ms)
        if created_at_unix_ms < as_of_unix_ms:
            raise ObserverCampaignCoordinatorError(
                "created_at_unix_ms cannot precede cycle as_of_unix_ms"
            )

        state, checkpoint = self._load_state_and_checkpoint()
        if as_of_unix_ms < state.last_cycle_at_unix_ms:
            raise ObserverCampaignCoordinatorError(
                "cycle timestamp cannot precede restored paper state"
            )
        if as_of_unix_ms == state.last_cycle_at_unix_ms:
            if checkpoint is None:
                raise ObserverCampaignCoordinatorError(
                    "cycle timestamp matches initial state but no completed checkpoint exists"
                )
            return _coordinator_idempotent_replay_result(state, as_of_unix_ms)

        cycle, _audit = assemble_observer_paper_campaign_cycle(
            self._observer_database_path,
            state,
            as_of_unix_ms,
            self._policy_bundle,
            self._risk_environment,
            self._selection_policy,
            recent_performance=self._recent_performance,
            global_risk_halt=self._global_risk_halt,
        )

        try:
            result = run_paper_cycle(state, cycle)
        except (TypeError, ValueError) as error:
            raise ObserverCampaignCoordinatorError(
                f"sealed paper cycle execution failed: {error}"
            ) from error

        self._require_accounting_not_invalid(result.next_state, "cycle result")

        try:
            evidence = self._evidence_store.record_cycle(
                self._paper_run_id,
                self._candidate,
                result,
            )
        except (OSError, TypeError, ValueError) as error:
            raise ObserverCampaignCoordinatorError(
                f"paper evaluation evidence write failed: {error}"
            ) from error
        self._require_evidence_attribution(evidence)

        sequence = 1 if checkpoint is None else checkpoint.sequence + 1
        try:
            saved = save_paper_checkpoint(
                self._observer_database_path,
                self._paper_run_id,
                sequence,
                result.next_state,
                created_at_unix_ms,
            )
        except PaperCheckpointError as error:
            raise ObserverCampaignCoordinatorError(
                f"paper checkpoint write failed: {error}"
            ) from error

        restored = self._load_checkpoint()
        if restored is None or restored.sequence != saved.sequence:
            raise ObserverCampaignCoordinatorError(
                "paper checkpoint reload did not return the saved sequence"
            )
        restart_report = validate_restart_equivalence(
            result.next_state,
            restored.state,
        )
        if not restart_report.equivalent:
            raise ObserverCampaignCoordinatorError(
                "paper checkpoint restart equivalence failed"
            )
        self._require_accounting_not_invalid(restored.state, "restored checkpoint")
        return result

    def evaluated_trades(self):
        evidence = self._load_evidence()
        self._require_evidence_attribution(evidence)
        try:
            return self._evidence_store.evaluated_trades(
                self._paper_run_id,
                self._candidate.candidate_version,
            )
        except (OSError, TypeError, ValueError) as error:
            raise ObserverCampaignCoordinatorError(
                f"paper evaluation evidence normalization failed: {error}"
            ) from error

    def _load_state_and_checkpoint(
        self,
    ) -> tuple[PaperLoopState, PaperCheckpointRecord | None]:
        evidence = self._load_evidence()
        self._require_evidence_attribution(evidence)
        checkpoint = self._load_checkpoint()
        state = self._initial_state if checkpoint is None else checkpoint.state
        self._require_accounting_not_invalid(state, "restored state")
        return state, checkpoint

    def _load_checkpoint(self) -> PaperCheckpointRecord | None:
        try:
            return load_latest_paper_checkpoint(
                self._observer_database_path,
                self._paper_run_id,
            )
        except PaperCheckpointError as error:
            raise ObserverCampaignCoordinatorError(
                f"paper checkpoint load failed: {error}"
            ) from error

    def _load_evidence(self) -> PaperEvaluationLedger:
        try:
            return self._evidence_store.load()
        except (OSError, TypeError, ValueError) as error:
            raise ObserverCampaignCoordinatorError(
                f"paper evaluation evidence load failed: {error}"
            ) from error

    def _require_evidence_attribution(
        self,
        ledger: PaperEvaluationLedger,
    ) -> None:
        expected = (
            self._candidate.candidate_version,
            self._candidate.candidate_fingerprint_sha256,
            self._candidate.strategy_version,
        )
        values = (
            ledger.entry_provenance
            + ledger.executions
            + ledger.closures
            + ledger.orphan_costs
        )
        for value in values:
            if value.paper_run_id != self._paper_run_id:
                continue
            actual = (
                value.candidate_version,
                value.candidate_fingerprint_sha256,
                value.strategy_version,
            )
            if actual != expected:
                raise ObserverCampaignCoordinatorError(
                    "paper-run attribution conflicts with the registry candidate"
                )

    @staticmethod
    def _require_accounting_not_invalid(
        state: PaperLoopState,
        label: str,
    ) -> None:
        try:
            report = validate_paper_accounting(state)
        except (TypeError, ValueError) as error:
            raise ObserverCampaignCoordinatorError(
                f"{label} accounting validation failed: {error}"
            ) from error
        if report.status is AccountingValidationStatus.INVALID:
            raise ObserverCampaignCoordinatorError(
                f"{label} accounting is invalid"
            )


def _coordinator_idempotent_replay_result(
    state: PaperLoopState,
    as_of_unix_ms: int,
) -> PaperCycleResult:
    return PaperCycleResult(
        policy_version=state.loop_policy.version,
        as_of_unix_ms=as_of_unix_ms,
        next_state=state,
        pending_entry_result=None,
        entry_results=(),
        exit_results=(),
        findings=(
            PaperLoopFinding(
                PaperLoopReasonCode.CYCLE_APPLIED,
                "exact completed aggregate paper cycle replay is idempotent",
            ),
        ),
    )
