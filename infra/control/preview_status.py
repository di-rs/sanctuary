"""Publish a PR link after the public gateway serves the requested commit."""

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

from .preview import eligible
from .release import preview_number, sha
from .runtime import DNS


def main() -> None:
    import hashlib

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    args = parser.parse_args()
    number = preview_number(args.name)
    repo, expected = os.environ["GITHUB_REPOSITORY"], sha(os.environ["BUILT_HEAD"], 40)
    zone = os.environ["PREVIEW_ZONE"]
    if not DNS.fullmatch(zone):
        raise ValueError("invalid preview zone")
    url = f"https://{args.name}.{zone}"
    identifier = hashlib.sha256(f"pull-request:{number}".encode()).hexdigest()[:32]
    for _ in range(60):
        try:
            with urllib.request.urlopen(
                f"{url}/api/environments/{identifier}", timeout=5
            ) as response:
                metadata = json.loads(response.read(131073))
            if metadata.get("sha") == expected and metadata.get("pr") == number:
                break
        except (OSError, ValueError):
            pass
        time.sleep(10)
    else:
        raise SystemExit("The host has not served the expected preview revision yet")
    active, _, head = eligible(repo, number)
    if not active or head != expected:
        return
    context = "Sanctuary / Playground"
    latest = subprocess.check_output(
        [
            "gh",
            "api",
            f"repos/{repo}/commits/{head}/status",
            "--jq",
            '.statuses[] | select(.context == "Sanctuary / Playground") | .target_url',
        ],
        text=True,
    )
    if latest.splitlines()[:1] != [url]:
        subprocess.run(
            [
                "gh",
                "api",
                "--silent",
                "--method",
                "POST",
                f"repos/{repo}/statuses/{head}",
                "-f",
                "state=success",
                "-f",
                "context=" + context,
                "-f",
                "target_url=" + url,
                "-f",
                "description=Open the Playground for this commit",
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
