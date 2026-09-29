from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .fast_paper_cutover_authorization import (
    FastPaperCutoverAuthorizationError,
    read_fast_paper_cutover_authorization,
    verify_fast_paper_cutover_authorization,
)
from .fast_paper_release_authorization import (
    FastPaperReleaseAuthorizationError,
    read_fast_paper_release_authorization,
    verify_fast_paper_release_authorization,
)


class FastPaperProductionAuthorizationError(RuntimeError):
    pass


def read_and_verify_fast_paper_production_authorization(
    path: str | Path,
    *,
    manifest,
    binding,
    execution_policy,
) -> dict[str, object]:
    errors: list[BaseException] = []
    for reader, verifier in (
        (
            read_fast_paper_cutover_authorization,
            verify_fast_paper_cutover_authorization,
        ),
        (
            read_fast_paper_release_authorization,
            verify_fast_paper_release_authorization,
        ),
    ):
        try:
            document = reader(path)
            verifier(
                document,
                manifest=manifest,
                binding=binding,
                execution_policy=execution_policy,
            )
            return dict(document)
        except (
            FastPaperCutoverAuthorizationError,
            FastPaperReleaseAuthorizationError,
        ) as exc:
            errors.append(exc)
    raise FastPaperProductionAuthorizationError(
        "production Fast PAPER authorization is not a valid cutover or release authorization"
    ) from errors[-1]


def authorization_fingerprint(
    document: Mapping[str, object],
) -> str:
    value = document.get("authorization_fingerprint_sha256")
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FastPaperProductionAuthorizationError(
            "production authorization fingerprint is invalid"
        )
    return value
