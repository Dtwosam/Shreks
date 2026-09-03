from __future__ import annotations

import inspect

import shreks_brain.fast_learning as fast_learning
import shreks_brain.fast_learning.codec as codec
import shreks_brain.fast_learning.inference as inference
import shreks_brain.fast_learning.trainer as trainer


def test_fast_learning_public_surface_has_no_execution_or_promotion_authority() -> None:
    forbidden_public_names = {
        "TradeIntent",
        "create_trade_intent",
        "submit",
        "send_transaction",
        "sign",
        "Signer",
        "provider",
        "execute",
        "paper_execute",
        "promote",
        "champion",
        "enable_live",
        "private_key",
    }
    assert forbidden_public_names.isdisjoint(set(dir(fast_learning)))


def test_fast_learning_sources_do_not_import_forbidden_authority() -> None:
    source = "\n".join(
        inspect.getsource(module) for module in (trainer, inference, codec)
    )
    for forbidden in (
        "shreks_brain.promotion",
        "shreks_brain.registry",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "RuntimeMode::Live",
        "send_transaction",
        "private_key",
        "shreks_providers",
    ):
        assert forbidden not in source
