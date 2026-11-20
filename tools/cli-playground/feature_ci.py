"""Select a feature deployment from live GitHub PR state using trusted checkout code."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


def api(path: str) -> Any:
    return json.loads(subprocess.check_output(["gh", "api", path]))


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


if __name__ == "__main__":
    repo = os.environ["GITHUB_REPOSITORY"]
    pr = int(os.environ["FEATURE_PR"])
    sha = os.environ.get("FEATURE_SHA") or api(f"repos/{repo}/pulls/{pr}")["head"]["sha"]
    operation, deployment = selection(repo, pr, sha)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        print(f"operation={operation}\nsha={sha}\ndeployment={deployment or ''}", file=output)
