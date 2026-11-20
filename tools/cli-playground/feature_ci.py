"""Reconcile a Playground app preview from trusted default-branch code."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]


def api(path: str, body: dict[str, object] | None = None) -> Any:
    args = ["gh", "api", path]
    if body is not None:
        args.extend(["--method", "POST", "--input", "-"])
    return json.loads(
        subprocess.check_output(args, input=json.dumps(body) if body else None, text=True)
    )


def app_source(path: str) -> bool:
    return path.startswith(
        (
            "tools/cli-playground/frontend/",
            "tools/cli-playground/src/",
            "tools/cli-playground/infra/docker/",
        )
    ) or path in {
        ".python-version",
        "pyproject.toml",
        "uv.lock",
        "tools/cli-playground/alembic.ini",
        "tools/cli-playground/pyproject.toml",
    }


def selection(repo: str, pr: int, sha: str) -> tuple[str, int | None]:
    current = api(f"repos/{repo}/pulls/{pr}")
    if current["head"]["sha"] != sha:
        return "skip", None
    if current["state"] == "open" and current["base"]["ref"] == "master":
        # GitHub caps the files endpoint at 3,000; do not silently miss a relevant file.
        if current["changed_files"] > 3000:
            return "deploy", None
        names = subprocess.check_output(
            [
                "gh",
                "api",
                "--paginate",
                f"repos/{repo}/pulls/{pr}/files?per_page=100",
                "--jq",
                ".[] | (.filename, (.previous_filename // empty))",
            ],
            text=True,
        )
        if any(app_source(name) for name in names.splitlines()):
            return "deploy", None
    query = urlencode({"environment": f"cli-playground/feature-pr-{pr}", "per_page": 1})
    records = api(f"repos/{repo}/deployments?{query}")
    if records:
        deployment = int(records[0]["id"])
        statuses = api(f"repos/{repo}/deployments/{deployment}/statuses?per_page=1")
        if not statuses or statuses[0]["state"] != "inactive":
            return "remove", deployment
    return "skip", None


def seed(sha: str, destination: Path) -> None:
    # This executable is a demo input for a frontend/backend PR. CLI changes still
    # go through the independent CLI preview publisher.
    binary = ROOT / "target/release/echor"
    schema = json.loads(
        subprocess.check_output([binary, "--help"], env={**os.environ, "SANCTUARY_CLI_SCHEMA": "1"})
    )
    catalog = {
        "schema_version": 1,
        "head_sha": sha,
        "base_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "clis": [
            {
                "name": "echor",
                "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "head": schema,
                "base": schema,
                "comparison": "available",
            }
        ],
    }
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(binary, "echor")
        archive.writestr("catalog.json", json.dumps(catalog))


def apply(repo: str, pr: int, sha: str, expected: str, bundle: Path) -> None:
    operation, deployment = selection(repo, pr, sha)
    if operation != expected:
        print("PR changed during the build; skipping the superseded operation.")
        return
    environment = f"cli-playground/feature-pr-{pr}"
    if operation == "deploy":
        deployment = int(
            api(
                f"repos/{repo}/deployments",
                {
                    "ref": sha,
                    "environment": environment,
                    "auto_merge": False,
                    "required_contexts": [],
                    "transient_environment": True,
                    "production_environment": False,
                },
            )["id"]
        )
    if not deployment:
        raise ValueError("missing deployment ID")
    statuses = f"repos/{repo}/deployments/{deployment}/statuses"
    log_url = f"{os.environ['GITHUB_SERVER_URL']}/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    api(statuses, {"state": "in_progress", "log_url": log_url})
    try:
        with tempfile.TemporaryDirectory() as private:
            directory = Path(private)
            config = directory / "config"
            host = os.environ["DEPLOY_HOST"]
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]+", host):
                raise ValueError("invalid deployment host")
            for filename, value in (
                ("key", os.environ["DEPLOY_SSH_KEY"]),
                ("known_hosts", os.environ["DEPLOY_KNOWN_HOSTS"]),
            ):
                path = directory / filename
                path.write_text(value.rstrip() + "\n")
                path.chmod(0o600)
            config.write_text(
                f"Host deployment\n  HostName {host}\n  User root\n  IdentityFile {directory}/key\n"
                f"  UserKnownHostsFile {directory}/known_hosts\n  StrictHostKeyChecking yes\n"
                "  IdentitiesOnly yes\n  BatchMode yes\n  ConnectTimeout 15\n  ServerAliveInterval 30\n"
            )
            ssh = [
                "ssh",
                "-F",
                str(config),
                "deployment",
                "bash",
                "/opt/sanctuary/cli-playground/scripts/feature.sh",
            ]
            if operation == "remove":
                subprocess.run([*ssh, "remove", str(pr)], check=True)
                api(statuses, {"state": "inactive", "log_url": log_url})
            else:
                tag = f"localhost/sanctuary-playground-pr-{pr}:{sha}"
                size = subprocess.check_output(
                    ["docker", "image", "inspect", "--format", "{{.Size}}", tag]
                )
                if int(size) > 1024**3:
                    raise ValueError("Feature image exceeds the 1 GiB limit")
                subprocess.run([*ssh, "reserve", str(pr)], check=True)
                image = subprocess.check_output(
                    ["bash", ROOT / "infra/environments/single-host/send-image.sh", config, tag],
                    text=True,
                ).strip()
                if not re.fullmatch(
                    rf"localhost/sanctuary-playground-pr-{pr}:[a-f0-9]{{64}}", image
                ):
                    raise ValueError("unexpected loaded image reference")
                if selection(repo, pr, sha)[0] != "deploy":
                    api(
                        statuses,
                        {
                            "state": "error",
                            "description": "Superseded before deployment",
                            "log_url": log_url,
                        },
                    )
                    return
                with bundle.open("rb") as stream:
                    url = subprocess.check_output(
                        [*ssh, "deploy", str(pr), sha, image], stdin=stream, text=True
                    ).strip()
                if not re.fullmatch(rf"https://app-pr-{pr}\.[a-z0-9.-]+/p/[a-f0-9]{{32}}", url):
                    raise ValueError("unexpected feature environment URL")
                api(
                    statuses,
                    {
                        "state": "success",
                        "environment_url": url,
                        "log_url": log_url,
                        "auto_inactive": True,
                    },
                )
                print(f"Playground feature environment: {url}")
    except Exception:
        api(statuses, {"state": "failure", "log_url": log_url})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("select", "seed", "apply"))
    args = parser.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    pr = int(os.environ["FEATURE_PR"])
    if not 1 <= pr < 10**10:
        parser.error("invalid PR number")
    sha = os.environ.get("FEATURE_SHA", "")
    if not sha and args.command == "select":
        sha = api(f"repos/{repo}/pulls/{pr}")["head"]["sha"]
    if not re.fullmatch("[0-9a-f]{40}", sha):
        parser.error("invalid PR identity")
    bundle = Path(os.environ["RUNNER_TEMP"]) / "feature-seed.zip"
    if args.command == "select":
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as result:
            print(f"operation={selection(repo, pr, sha)[0]}", file=result)
            print(f"sha={sha}", file=result)
    elif args.command == "seed":
        seed(sha, bundle)
    else:
        apply(repo, pr, sha, os.environ["FEATURE_OPERATION"], bundle)


if __name__ == "__main__":
    main()
