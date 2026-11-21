"""Publish release manifests from trusted workflow code. Previews carry binary ZIPs only."""

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from .bucket import Bucket
from .preview import eligible
from .release import IMAGES, MAX_BUNDLE, MAX_IMAGE, SERVICES, Release, digest, preview_number, sha
from .runtime import DNS


def output(**values: object) -> None:
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
        for key, value in values.items():
            print(f"{key}={value}", file=stream)


def commit_record(bucket: Bucket, value: Release, temp: Path) -> None:
    temp.write_bytes(value.encode())
    if value.name in SERVICES:
        bucket.put(f"history/{value.name}/{value.commit}.json", temp)
    bucket.put(f"desired/{value.name}.json", temp)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("list", "plan", "finish", "release", "rollback"))
    parser.add_argument("name", nargs="?")
    args = parser.parse_args()
    bucket = Bucket()
    repo = os.environ["GITHUB_REPOSITORY"]
    with tempfile.TemporaryDirectory() as folder:
        temp = Path(folder) / "record"
        if args.action == "list":
            requested = os.environ.get("PR_NUMBER")
            if requested:
                numbers = [preview_number("pr-" + requested)]
            else:
                prs = subprocess.check_output(
                    [
                        "gh",
                        "api",
                        "--paginate",
                        f"repos/{repo}/pulls?state=open&per_page=100",
                        "--jq",
                        ".[] | select(.head.repo.full_name == .base.repo.full_name) | .number",
                    ],
                    text=True,
                )
                numbers = sorted(
                    {int(n) for n in prs.split()}
                    | {preview_number(Path(key).stem) for key in bucket.names("desired/pr-")}
                )
            output(numbers=json.dumps(numbers, separators=(",", ":")))
            return
        name = args.name or ""
        if args.action in {"release", "rollback"}:
            if name not in SERVICES:
                raise ValueError("unknown service")
            rev = sha(os.environ["RELEASE_COMMIT"], 40)
            history = f"history/{name}/{rev}.json"
            if args.action == "rollback" or history in bucket.names(history):
                bucket.get(history, temp, 4096)
                value = Release.decode(name, temp.read_bytes())
                if value.commit != rev:
                    raise ValueError("history revision mismatch")
                bucket.put(f"desired/{name}.json", temp)
                return
            blobs = {
                image: bucket.publish_blob(
                    Path(os.environ["RUNNER_TEMP"]) / f"{image}.tar.gz", MAX_IMAGE
                )
                for image in IMAGES.get(name, ())
            }
            if name == "playground":
                blobs["bundle"] = bucket.publish_blob(
                    Path(os.environ["RUNNER_TEMP"]) / "bundle.zip", MAX_BUNDLE
                )
            commit_record(bucket, Release(name, rev, blobs), temp)
            return
        number = preview_number(name)
        active, base, current = eligible(repo, number)
        desired = f"desired/{name}.json"
        incoming = (
            f"incoming/{name}/{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}.zip"
        )
        expires = int(time.time()) + 86400
        if not active:
            bucket.api("delete-object", "--key", desired)
            output(build="false")
            return
        zone = os.environ["PREVIEW_ZONE"]
        if not DNS.fullmatch(zone):
            raise ValueError("invalid preview DNS zone")
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary:
            print(
                f"Playground for PR #{number}, commit `{current}`: https://{name}.{zone}/",
                file=summary,
            )
        if args.action == "plan":
            if desired in bucket.names(desired):
                bucket.get(desired, temp, 4096)
                prior = Release.decode(name, temp.read_bytes())
                if prior.commit == current:
                    commit_record(bucket, Release(name, current, prior.blobs, expires), temp)
                    output(build="false", head=current)
                    return
            # boto3 is installed in the trusted planning job only.
            from importlib import import_module

            boto3 = import_module("boto3")
            config = import_module("botocore.config")

            client = boto3.client(
                "s3",
                endpoint_url=bucket.endpoint,
                region_name="auto",
                config=config.Config(
                    signature_version="s3v4", request_checksum_calculation="when_required"
                ),
            )
            url = client.generate_presigned_url(
                "put_object",
                Params={"Bucket": bucket.name, "Key": incoming},
                ExpiresIn=7200,
                HttpMethod="PUT",
            )
            # Keep the capability outside the checkout, container mounts, logs and job outputs.
            from .keys import write_atomic

            write_atomic(Path(os.environ["RUNNER_TEMP"]) / "put.conf", f'url = "{url}"\n'.encode())
            output(build="true", head=current, base=base)
        elif sha(os.environ["BUILT_HEAD"], 40) == current:
            bundle = Path(folder) / "bundle.zip"
            bucket.get(incoming, bundle, MAX_BUNDLE)
            blob = digest(bundle)
            if blob != sha(os.environ["BUILT_DIGEST"], 64):
                raise ValueError("preview upload digest mismatch")
            # Re-read after the upload and compare the complete diff again.
            live, _, latest = eligible(repo, number)
            if live and latest == current:
                bucket.put("blobs/" + blob, bundle)
                commit_record(bucket, Release(name, current, {"bundle": blob}, expires), temp)
            elif not live:
                bucket.api("delete-object", "--key", desired)
            bucket.api("delete-object", "--key", incoming)


if __name__ == "__main__":
    main()
