import inspect

import shreks_brain.paper_validation as paper_validation


EXPECTED_PUBLIC_API = (
    "FAST_PAPER_CHECKPOINT_SCHEMA_VERSION",
    "FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION",
    "FAST_PAPER_PROTECTED_RUNTIME_STATE_VERSION",
    "FAST_PAPER_RUNTIME_STATE_VERSION",
    "AccountingFinding",
    "AccountingFindingCode",
    "AccountingValidationReport",
    "AccountingValidationStatus",
    "FastPaperCheckpointError",
    "FastPaperCheckpointRecord",
    "FastPaperProtectedCheckpointRecord",
    "FastPaperProtectedRuntimeState",
    "FastPaperRestartValidationReport",
    "FastPaperRuntimeState",
    "PaperCheckpointError",
    "PaperCheckpointRecord",
    "RestartValidationReport",
    "decode_fast_paper_checkpoint",
    "decode_fast_paper_protected_checkpoint",
    "decode_paper_checkpoint",
    "encode_fast_paper_checkpoint",
    "encode_fast_paper_protected_checkpoint",
    "encode_paper_checkpoint",
    "load_latest_fast_paper_checkpoint",
    "load_latest_fast_paper_protected_checkpoint",
    "load_latest_paper_checkpoint",
    "save_fast_paper_checkpoint",
    "save_fast_paper_protected_checkpoint",
    "save_paper_checkpoint",
    "validate_fast_paper_accounting",
    "validate_fast_paper_protected_restart_equivalence",
    "validate_fast_paper_restart_equivalence",
    "validate_paper_accounting",
    "validate_paper_ledger",
    "validate_restart_equivalence",
)


def test_paper_validation_public_api_is_exact_and_stable() -> None:
    assert paper_validation.__all__ == EXPECTED_PUBLIC_API
    for name in EXPECTED_PUBLIC_API:
        assert getattr(paper_validation, name) is not None


def test_public_api_exposes_no_provider_signer_transaction_or_live_authority() -> None:
    forbidden = (
        "provider",
        "rpc",
        "signer",
        "secret",
        "private_key",
        "transaction",
        "send_transaction",
        "live_execution",
    )
    for name in EXPECTED_PUBLIC_API:
        value = getattr(paper_validation, name)
        surface = f"{name} {getattr(value, '__module__', '')}"
        if inspect.isfunction(value) or inspect.isclass(value):
            surface += f" {getattr(value, '__qualname__', '')}"
        lowered = surface.lower()
        assert not any(token in lowered for token in forbidden)
