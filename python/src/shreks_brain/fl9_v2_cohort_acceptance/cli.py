from __future__ import annotations

import argparse

from shreks_brain.fl9_tradable_universe import (
    Fl9TradableUniverseStore,
)

from .artifact import (
    encode_manifest_for_stdout,
    write_fl9_v2_cohort_acceptance,
)
from .builder import build_fl9_v2_cohort_acceptance
from .models import (
    Fl9V2CohortAcceptancePolicy,
    Fl9V2CohortEvidenceFloorPolicy,
)
from .source import SqliteFl9V2CohortSource


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-fl9-v2-cohort-acceptance",
        description=(
            "Build the frozen input-only FL9 V2 cohort-acceptance artifact "
            "from the read-only production observer database."
        ),
    )
    parser.add_argument("--database", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    policy = Fl9V2CohortAcceptancePolicy()
    floor_policy = Fl9V2CohortEvidenceFloorPolicy()
    source = SqliteFl9V2CohortSource(args.database)
    tradable_store = Fl9TradableUniverseStore(args.database)

    semantic = build_fl9_v2_cohort_acceptance(
        source=source,
        tradable_store=tradable_store,
        policy=policy,
        floor_policy=floor_policy,
    )
    artifact = write_fl9_v2_cohort_acceptance(
        semantic,
        args.destination,
        policy=policy,
        floor_policy=floor_policy,
    )
    print(
        encode_manifest_for_stdout(artifact.manifest),
        end="",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
