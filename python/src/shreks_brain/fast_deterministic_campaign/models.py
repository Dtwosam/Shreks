from __future__ import annotations

from dataclasses import dataclass

from shreks_brain.fast_campaign_paper import FastCampaignPaperDecisionEvidence
from shreks_brain.fast_deterministic_offline import (
    FastOfflineGraduationFlowEvidence,
    FastOfflineImpulseScalpEvidence,
    FastOfflineLongerRunnerEvidence,
    FastOfflineMicroPullbackEvidence,
    FastOfflinePreGraduationEvidence,
    FastOfflineRowEvidence,
    FastOfflineWalletCohortEvidence,
)
from shreks_brain.research.fast_training_features import FastTrainingFeatureRecord


_EVIDENCE_TYPES = (
    FastOfflineImpulseScalpEvidence,
    FastOfflineMicroPullbackEvidence,
    FastOfflinePreGraduationEvidence,
    FastOfflineGraduationFlowEvidence,
    FastOfflineWalletCohortEvidence,
    FastOfflineLongerRunnerEvidence,
)


@dataclass(frozen=True, slots=True)
class FastDeterministicCampaignRow:
    record: FastTrainingFeatureRecord
    flat_evidence: FastOfflineRowEvidence
    open_evidence: FastOfflineRowEvidence
    paper_evidence: FastCampaignPaperDecisionEvidence

    def __post_init__(self) -> None:
        if type(self.record) is not FastTrainingFeatureRecord:
            raise ValueError("record must be exact FastTrainingFeatureRecord")
        if type(self.flat_evidence) not in _EVIDENCE_TYPES:
            raise ValueError(
                "flat_evidence must be an exact supported offline row evidence value"
            )
        if type(self.open_evidence) not in _EVIDENCE_TYPES:
            raise ValueError(
                "open_evidence must be an exact supported offline row evidence value"
            )
        if type(self.paper_evidence) is not FastCampaignPaperDecisionEvidence:
            raise ValueError(
                "paper_evidence must be exact FastCampaignPaperDecisionEvidence"
            )
