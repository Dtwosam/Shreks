from .models import (
    FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION,
    FL9_V2_COHORT_ACCEPTANCE_SCHEMA_NAME,
    FL9_V2_COHORT_ACCEPTANCE_SCHEMA_VERSION,
    FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION,
    Fl9V2AcceptedDecision,
    Fl9V2CohortAcceptanceArtifact,
    Fl9V2CohortAcceptanceManifest,
    Fl9V2CohortAcceptancePolicy,
    Fl9V2CohortEvidenceFloorPolicy,
    Fl9V2ConcentrationSummary,
    Fl9V2CoverageSessionCheckpoint,
    Fl9V2QuarantinedDecision,
)
from .source import SqliteFl9V2CohortSource


__all__ = (
    "FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION",
    "FL9_V2_COHORT_ACCEPTANCE_SCHEMA_NAME",
    "FL9_V2_COHORT_ACCEPTANCE_SCHEMA_VERSION",
    "FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION",
    "Fl9V2CoverageSessionCheckpoint",
    "Fl9V2CohortEvidenceFloorPolicy",
    "Fl9V2CohortAcceptancePolicy",
    "Fl9V2ConcentrationSummary",
    "Fl9V2AcceptedDecision",
    "Fl9V2QuarantinedDecision",
    "Fl9V2CohortAcceptanceManifest",
    "Fl9V2CohortAcceptanceArtifact",
    "SqliteFl9V2CohortSource",
    "build_fl9_v2_cohort_acceptance",
    "write_fl9_v2_cohort_acceptance",
    "read_fl9_v2_cohort_acceptance",
)


def __getattr__(name: str):
    if name == "build_fl9_v2_cohort_acceptance":
        from .builder import build_fl9_v2_cohort_acceptance

        return build_fl9_v2_cohort_acceptance
    if name in {
        "write_fl9_v2_cohort_acceptance",
        "read_fl9_v2_cohort_acceptance",
    }:
        from .artifact import (
            read_fl9_v2_cohort_acceptance,
            write_fl9_v2_cohort_acceptance,
        )

        return {
            "write_fl9_v2_cohort_acceptance": (
                write_fl9_v2_cohort_acceptance
            ),
            "read_fl9_v2_cohort_acceptance": (
                read_fl9_v2_cohort_acceptance
            ),
        }[name]
    raise AttributeError(name)
