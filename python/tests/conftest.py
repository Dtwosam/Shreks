from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _pin_legacy_g2_release_manager_tests_to_their_declared_platform(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
):
    """Keep legacy G2 manager tests architecture-independent.

    The historical test module intentionally builds x86_64 fixtures. Once the
    production release manager starts enforcing host/platform equality, those
    fixtures must remain valid on GitHub's ARM64 runner as well as x86_64 CI.
    ARM64 host mapping and mismatch behavior are tested separately in the
    dedicated compatibility contract.
    """
    if request.path.name != "test_g2_release_manager.py":
        return

    manager = getattr(request.module, "release_manager", None)
    declared_platform = getattr(request.module, "PLATFORM", None)
    if manager is None or declared_platform is None:
        return

    monkeypatch.setattr(
        manager,
        "_host_release_platform",
        lambda: declared_platform,
        raising=False,
    )
