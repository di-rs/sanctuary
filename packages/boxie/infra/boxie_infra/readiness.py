"""Poll local Boxie API readiness from inside the container after deployment."""

import argparse
import json
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen

CONSUMER_CREDENTIAL = Path("/run/secrets/consumer")


def wait_for_readiness(*, check_release: bool) -> None:
    request = Request(
        "http://127.0.0.1:8090/readyz",
        headers={"Authorization": f"Bearer {CONSUMER_CREDENTIAL.read_text().strip()}"},
    )
    retryable = (OSError,) if check_release else (OSError, ValueError, KeyError)
    for _ in range(30):
        try:
            with urlopen(request, timeout=3) as response:
                data = json.load(response)
            if check_release:
                ready = data["release"] == os.environ["BOXIE_RELEASE"] and all(
                    data["dependencies"].values()
                )
            else:
                ready = response.status == 200 and data["dependencies"]["orchestration"] is True
            if ready:
                return
        except retryable:
            pass
        time.sleep(2)
    target = "dependencies" if check_release else "orchestration"
    raise SystemExit(f"Boxie {target} did not become ready")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("release", "sandbox"))
    wait_for_readiness(check_release=parser.parse_args().mode == "release")
