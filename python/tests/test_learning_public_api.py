from __future__ import annotations

import shreks_brain.learning as learning


def test_learning_public_api_is_explicit() -> None:
    assert learning.__all__ == (
        "MODEL_TRAINING_SCHEMA_VERSION",
        "ModelFamily",
        "ClassWeightMode",
        "ResearchReturnTarget",
        "LogisticRegressionTrainingPolicy",
        "ModelTrainingRequest",
        "FeatureTransform",
        "TrainedLogisticRegressionModel",
        "ModelPrediction",
    )
