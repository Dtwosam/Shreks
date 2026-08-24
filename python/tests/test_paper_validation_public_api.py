import inspect

import shreks_brain.paper_validation as paper_validation


EXPECTED_PUBLIC_API = (
    "AccountingFinding",
    "AccountingFindingCode",
    "AccountingValidationReport",
    "AccountingValidationStatus",
    "PaperCheckpointError",
    "PaperCheckpointRecord",
    "RestartValidationReport",
    "decode_paper_checkpoint",
    "encode_paper_checkpoint",
    "load_latest_paper_checkpoint",
    "save_paper_checkpoint",
    "validate_paper_accounting",
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
