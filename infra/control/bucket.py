"""Private R2 objects using the AWS CLI supplied by CI and the host image."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .release import digest


class Bucket:
    def __init__(self) -> None:
        self.name = os.environ["SANCTUARY_R2_BUCKET"]
        account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
        if len(account) != 32 or any(c not in "0123456789abcdef" for c in account):
            raise ValueError("invalid Cloudflare account ID")
        self.endpoint = f"https://{account}.r2.cloudflarestorage.com"

    def api(self, *args: str) -> dict[str, Any]:
        response = subprocess.check_output(
            [
                "aws",
                "--region",
                "auto",
                "--endpoint-url",
                self.endpoint,
                "s3api",
                args[0],
                "--bucket",
                self.name,
                *args[1:],
                "--output",
                "json",
            ],
            env=os.environ
            | {
                "AWS_PAGER": "",
                "AWS_EC2_METADATA_DISABLED": "true",
                "AWS_REQUEST_CHECKSUM_CALCULATION": "when_required",
                "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_required",
            },
        )
        return dict(json.loads(response or b"{}"))

    def names(self, prefix: str) -> list[str]:
        listing = self.api("list-objects-v2", "--prefix", prefix)
        return [item["Key"] for item in listing.get("Contents", [])]

    def put(self, key: str, path: Path) -> None:
        self.api("put-object", "--key", key, "--body", str(path))

    def get(self, key: str, destination: Path, limit: int) -> None:
        info = self.api("head-object", "--key", key)
        if not 0 < info["ContentLength"] <= limit:
            raise ValueError("R2 object exceeds the allowed size")
        self.api("get-object", "--key", key, "--if-match", info["ETag"], str(destination))
        if destination.stat().st_size != info["ContentLength"]:
            raise ValueError("incomplete object transfer")

    def publish_blob(self, path: Path, limit: int) -> str:
        if not 0 < path.stat().st_size <= limit:
            raise ValueError("invalid blob size")
        identity = digest(path)
        self.put("blobs/" + identity, path)
        return identity
