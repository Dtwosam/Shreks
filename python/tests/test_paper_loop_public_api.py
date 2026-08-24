from dataclasses import fields, is_dataclass
import inspect

import shreks_brain.paper_loop as paper_loop
from shreks_brain.runtime import RuntimeMode


EXPECTED_PUBLIC_API = (
    "FirstPullbackSetupInput",
    "FreshLaunchSetupInput",
    "GraduationBreakoutSetupInput",
    "ManagedPaperPosition",
    "PaperCycleInput",
    "PaperCycleResult",
    "PaperEntryCandidate",
    "PaperEntryResult",
    "PaperExitObservation",
    "PaperExitResult",
    "PaperLoopFinding",
    "PaperLoopPolicy",
    "PaperLoopReasonCode",
    "PaperLoopState",
    "PaperPendingEntryResult",
    "PendingPaperEntry",
    "create_paper_loop_state",
    "run_paper_cycle",
)


def test_paper_loop_public_api_is_exact_and_stable() -> None:
    assert paper_loop.__all__ == EXPECTED_PUBLIC_API
    assert tuple(name for name in EXPECTED_PUBLIC_API if hasattr(paper_loop, name)) == EXPECTED_PUBLIC_API


def test_public_api_exposes_no_provider_storage_signer_transaction_or_live_authority() -> None:
    forbidden = (
        "provider",
        "rpc",
        "sqlite",
        "database",
        "storage",
        "signer",
        "secret",
        "private_key",
        "transaction",
        "submit",
        "send_transaction",
        "live_execution",
    )
    for name in EXPECTED_PUBLIC_API:
        value = getattr(paper_loop, name)
        surface = name.lower()
        if is_dataclass(value):
            surface += " " + " ".join(field.name.lower() for field in fields(value))
        elif callable(value):
            surface += " " + str(inspect.signature(value)).lower()
        assert not any(fragment in surface for fragment in forbidden), (name, surface)


def test_paper_loop_does_not_reexport_runtime_modes_or_trade_execution_primitives() -> None:
    for name in (
        "RuntimeMode",
        "TradeIntent",
        "TradeSide",
        "PaperQuote",
        "PaperFill",
        "execute_paper_intent",
        "apply_paper_execution",
        "assess_exit",
    ):
        assert not hasattr(paper_loop, name)
    assert RuntimeMode.LIVE.value == "LIVE"
