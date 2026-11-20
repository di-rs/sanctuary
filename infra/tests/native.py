"""Exercise the deployment controller on an isolated Linux amd64 runner with runsc."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from boxie_test_support.terminal_network import attach
from cli_playground.domain import identifier
from websockets.asyncio.client import connect
from websockets.typing import Origin

from infra.control.bucket import Bucket
from infra.control.host import Host
from infra.control.release import Release, digest
from infra.control.runtime import Site


async def exercise_terminal(site: Site, name: str, number: int, revision: str) -> None:
    hostname = (
        os.environ["PLAYGROUND_HOST"]
        if number == 0
        else f"pr-{number}.{os.environ['PREVIEW_ZONE']}"
    )
    container = f"{site.site}-{name}-web-1"
    networks = json.loads(subprocess.check_output(["docker", "inspect", container]))[0][
        "NetworkSettings"
    ]["Networks"]
    address = networks[site.site + "-web"]["IPAddress"]
    origin = "https://" + hostname
    page = identifier(number)
    path = f"/api/environments/{page}/sessions"
    async with httpx.AsyncClient(
        base_url=f"http://{address}:8000",
        headers={"Host": hostname, "Origin": origin},
        trust_env=False,
        timeout=30,
    ) as client:
        response = await client.post(path, json={"revision": revision})
        response.raise_for_status()
        binding = response.json()
        query = urlencode({"session_id": binding["id"], "revision": revision})
        async with (
            asyncio.timeout(65),
            connect(
                f"ws://{hostname}/ws/{page}?{query}",
                host=address,
                port=8000,
                origin=Origin(origin),
                proxy=None,
            ) as socket,
        ):
            await socket.send(json.dumps({"type": "auth", "credential": binding["credential"]}))
            assert json.loads(await socket.recv())["type"] == "authenticated"
            epoch, _ = await attach(socket)
            # The marker appears as a single word only after the shell runs the bundled CLI.
            await socket.send(
                json.dumps(
                    {
                        "type": "input",
                        "epoch": epoch,
                        "source": "user",
                        "data": "echor sanctuary'healthy'\n",
                    }
                )
            )
            output = bytearray()
            while b"sanctuaryhealthy" not in output:
                frame = await socket.recv()
                if isinstance(frame, bytes):
                    output.extend(frame[8:])
        stopped = await client.delete(
            path + "/" + binding["id"], headers={"Authorization": "Bearer " + binding["credential"]}
        )
        stopped.raise_for_status()


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    project = "sanctuary-test-" + uuid4().hex[:8]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    bundle_path = Path(sys.argv[1])
    with tempfile.TemporaryDirectory(prefix=project + "-") as directory:
        root = Path(directory)
        state = root / "state"
        values = {
            "SANCTUARY_SITE": project,
            "SANCTUARY_STATE": str(state),
            "PLAYGROUND_HOST": "play.example.net",
            "PREVIEW_ZONE": "example.net",
            "GRAFANA_HOST": "grafana.example.net",
            "TEMPORAL_HOST": "temporal.example.net",
        }
        with patch.dict(os.environ, values):
            site = Site()
            site.network_setup()
            with patch.object(site, "config", return_value=repo / "infra/services"):
                host = Host(site, Mock(spec=Bucket))
                try:
                    subprocess.run(["sh", str(repo / "infra/control/credentials.sh")], check=True)
                    for service in ("postgres", "temporal"):
                        host.apply(Release(service, revision, {}))
                    images = {}
                    for image in ("boxie", "sandbox", "playground"):
                        archive = root / image
                        with archive.open("wb") as stream:
                            subprocess.run(
                                ["docker", "image", "save", f"sanctuary/{image}:{revision}"],
                                stdout=stream,
                                check=True,
                            )
                        images[image] = digest(archive)
                        archive.rename(state / "blobs" / images[image])
                    host.apply(
                        Release("boxie", revision, {k: images[k] for k in ("boxie", "sandbox")})
                    )
                    binary = digest(bundle_path)
                    with (
                        bundle_path.open("rb") as source,
                        (state / "blobs" / binary).open("wb") as destination,
                    ):
                        shutil.copyfileobj(source, destination)
                    host.apply(
                        Release(
                            "playground",
                            revision,
                            {"playground": images["playground"], "bundle": binary},
                        )
                    )
                    preview = Release("pr-7", revision, {"bundle": binary}, int(time.time()) + 3600)
                    host.apply(preview)
                    assert site.applied("pr-7") == preview
                    host.key_action("pr-7", "rotate")
                    host.gateway(preview, revision, "renew")
                    asyncio.run(exercise_terminal(site, "pr-7", 7, revision))
                    # The host retries retirement while Temporal finishes the asynchronous stop.
                    for attempt in range(15):
                        try:
                            host.remove("pr-7")
                            break
                        except subprocess.CalledProcessError:
                            if attempt == 14:
                                raise
                            time.sleep(2)
                    assert site.applied("pr-7") is None
                    assert not (state / "routes/pr-7.caddy").exists()
                    assert (state / "instances/playground/client/key").is_file()
                    asyncio.run(exercise_terminal(site, "playground", 0, revision))
                finally:
                    for name in ("pr-7", "playground", "boxie", "temporal", "postgres"):
                        try:
                            site.compose(name, revision, "down", "--volumes")
                        except subprocess.CalledProcessError:
                            # Early failure can precede creation of the project's env file.
                            if (
                                name in {"pr-7", "playground"}
                                and not (state / "instances" / name / "web.env").exists()
                            ):
                                continue
                            raise
                    for name in ("database", "temporal", "clients", "telemetry", "web", "admin"):
                        subprocess.run(
                            ["docker", "network", "rm", project + "-" + name], check=True
                        )


if __name__ == "__main__":
    main()
