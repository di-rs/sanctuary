"""Production supervisor bootstrap with test-only collection entry/completion markers.

The wrapper changes no collection timing, locking, deadline or deletion logic.
"""

from pathlib import Path

import boxie.bootstrap.supervisor
from boxie.persistence.postgres_artifacts import PostgresArtifactStore
from temporalio import activity


class ObservedArtifacts(PostgresArtifactStore):
    async def collect(self, limit: int = 100) -> int:
        if not activity.in_activity():
            return await super().collect(limit)
        marker = Path("/faults") / f"collection-{activity.info().workflow_run_id}"
        marker.with_suffix(".entered").touch()
        try:
            return await super().collect(limit)
        finally:
            marker.with_suffix(".completed").touch()


if __name__ == "__main__":
    vars(boxie.bootstrap.supervisor)["PostgresArtifactStore"] = ObservedArtifacts
    boxie.bootstrap.supervisor.main()
