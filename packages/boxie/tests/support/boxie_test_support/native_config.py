"""Write explicit operator configuration for the two private Boxie processes."""

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import UUID


def existing_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"expected an object in {path.name}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--installation-id", type=UUID, required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--consumer-id", default="smoke")
    parser.add_argument(
        "--job-profile",
        action="append",
        help="set this consumer's job grants (repeatable); omit to keep existing grants",
    )
    parser.add_argument("--supervisor-url", default="http://supervisor:8091")
    parser.add_argument("--bind-host", default="0.0.0.0")
    parser.add_argument("--supervisor-credential", default="/run/secrets/supervisor")
    parser.add_argument(
        "--consumer-credential",
        help="credential path for this consumer; defaults to its existing path or /run/secrets/consumer",
    )
    parser.add_argument("--profiles", default="/etc/boxie/profiles.json")
    parser.add_argument("--postgres-dsn", default="/run/secrets/postgres-dsn")
    parser.add_argument("--temporal-address", default="temporal:7233")
    parser.add_argument("--temporal-server-name", default="temporal")
    parser.add_argument("--temporal-namespace", default="boxie")
    args = parser.parse_args()
    if not args.data_dir.is_absolute():
        parser.error("--data-dir must be an absolute daemon-host path")
    args.output.mkdir(parents=True, exist_ok=True)
    previous_api = existing_config(args.output / "api.json")
    previous_supervisor = existing_config(args.output / "supervisor.json")
    credentials = previous_api.get("consumer_credential_files", {})
    credential = args.consumer_credential or credentials.get(
        args.consumer_id, "/run/secrets/consumer"
    )
    if any(name != args.consumer_id and path == credential for name, path in credentials.items()):
        parser.error(
            "another consumer uses this credential path; supply a distinct --consumer-credential"
        )
    credentials[args.consumer_id] = credential
    job_policy = previous_api.get("job_policy", {})
    if args.job_profile is not None:
        job_policy.setdefault("profile_grants", {})[args.consumer_id] = args.job_profile
    identity = {"installation_id": str(args.installation_id), "host_id": args.host_id}
    lifecycle = {
        "postgres_dsn_file": args.postgres_dsn,
        "temporal_address": args.temporal_address,
        "temporal_server_name": args.temporal_server_name,
        "temporal_namespace": args.temporal_namespace,
        "temporal_ca_file": "/run/secrets/temporal-ca.pem",
        "temporal_cert_file": "/run/secrets/temporal-client.pem",
        "temporal_key_file": "/run/secrets/temporal-client.key",
    }
    configurations = {
        "supervisor.json": {
            "data_dir": str(args.data_dir),
            "postgres_dsn_file": args.postgres_dsn,
            "lifecycle": lifecycle,
            "profiles_file": args.profiles,
            "credential_file": args.supervisor_credential,
            "identity": {"installation_id": str(args.installation_id), "host_id": args.host_id},
            "bind_host": args.bind_host,
        },
        "api.json": {
            "release": "local",
            "identity": identity,
            "lifecycle": lifecycle,
            "supervisor_url": args.supervisor_url,
            "supervisor_credential_file": args.supervisor_credential,
            "consumer_credential_files": credentials,
            "job_policy": job_policy,
            "bind_host": args.bind_host,
        },
    }
    if "policy_maximum" in previous_supervisor:
        configurations["supervisor.json"]["policy_maximum"] = previous_supervisor["policy_maximum"]
    for name, value in configurations.items():
        (args.output / name).write_text(json.dumps(value, indent=2) + "\n")


if __name__ == "__main__":
    main()
