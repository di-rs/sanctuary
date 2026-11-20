"""Stop and retire one consumer's resources after its application has been removed."""

import argparse
import asyncio
import sys
from pathlib import Path

import httpx
from sqlmodel import col, select

from boxie.bootstrap.api import load_configuration
from boxie.bootstrap.dependencies import database_for
from boxie.persistence.models import Artifact, Sandbox


async def retire(consumer: str, config: Path, bearer: str) -> None:
    settings = load_configuration(config)
    async with database_for(settings.lifecycle.postgres_dsn_file) as sessions, sessions() as db:
        sandboxes = (
            await db.exec(
                select(Sandbox.id).where(
                    Sandbox.consumer_id == consumer,
                    col(Sandbox.state).not_in(("terminated", "failed")),
                )
            )
        ).all()
        artifacts = (
            await db.exec(
                select(Artifact.id).where(
                    Artifact.consumer_id == consumer,
                    col(Artifact.retired).is_(False),
                )
            )
        ).all()
    # The normal private API checks ownership and durably schedules physical cleanup.
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{settings.bind_port}",
        headers={"Authorization": f"Bearer {bearer}"},
        trust_env=False,
        timeout=30,
    ) as api:
        for resource, identifiers in (("sandboxes", sandboxes), ("artifacts", artifacts)):
            for identifier in identifiers:
                result = await api.delete(f"/v1/{resource}/{identifier}")
                result.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("consumer")
    parser.add_argument("--config", type=Path, default=Path("/etc/boxie/api.json"))
    args = parser.parse_args()
    asyncio.run(retire(args.consumer, args.config, sys.stdin.readline().strip()))


if __name__ == "__main__":
    main()
