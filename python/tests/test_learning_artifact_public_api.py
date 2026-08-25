from __future__ import annotations

import subprocess
import sys

import shreks_brain.learning as learning
from shreks_brain.learning.store import ModelArtifactStore


def test_learning_exports_e9_model_artifact_store() -> None:
    assert learning.MODEL_ARTIFACT_STORE_SCHEMA_VERSION == "e9-model-artifacts-v1"
    assert learning.ModelArtifactStore is ModelArtifactStore
    assert "MODEL_ARTIFACT_STORE_SCHEMA_VERSION" in learning.__all__
    assert "ModelArtifactStore" in learning.__all__


def test_importing_learning_does_not_eagerly_import_sklearn() -> None:
    code = (
        "import sys; "
        "import shreks_brain.learning; "
        "assert 'sklearn' not in sys.modules, sorted("
        "name for name in sys.modules if name.startswith('sklearn'))"
    )

    subprocess.run([sys.executable, "-c", code], check=True)


def test_e9_store_exposes_no_promotion_trade_or_live_authority() -> None:
    forbidden = {
        "delete",
        "overwrite",
        "replace_model",
        "promote",
        "record_status",
        "trade",
        "create_trade_intent",
        "sign",
        "submit",
        "enable_live",
    }

    assert forbidden.isdisjoint(set(dir(ModelArtifactStore)))
    assert set(name for name in dir(ModelArtifactStore) if not name.startswith("_")) == {
        "append",
        "get",
        "load",
    }
