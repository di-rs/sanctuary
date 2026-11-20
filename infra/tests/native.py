"""Exercise the deployment controller on an isolated Linux amd64 runner with runsc."""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from infra.control.bucket import Bucket
from infra.control.host import Host
from infra.control.release import Release, digest
from infra.control.runtime import Site


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
                    host.remove("pr-7")
                    assert site.applied("pr-7") is None
                    assert not (state / "routes/pr-7.caddy").exists()
                    assert (state / "instances/playground/client/key").is_file()
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
