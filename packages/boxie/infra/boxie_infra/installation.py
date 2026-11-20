"""Render the fixed installation's private owner settings without printing them."""

import argparse
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path


def _replace_private_text(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def write_environment(path: Path, values: dict[str, str]) -> None:
    for name, value in values.items():
        if any(character in value for character in "\n\r\x00'$`\\"):
            raise ValueError(f"Invalid installation setting: {name}")
    _replace_private_text(path, "".join(f"{key}='{value}'\n" for key, value in values.items()))


def _render_template(source: Path, root: Path, values: Mapping[str, str], *keys: str) -> None:
    content = source.read_text()
    for key in keys:
        content = content.replace("${" + key + "}", values[key])
    target = root / source.name
    target.write_text(content)
    target.chmod(0o644)


def render(root: Path, source: Path) -> None:
    credentials = root / "boxie"
    tls = root / "tls"

    def secret(name: str) -> str:
        return (credentials / name).read_text().strip()

    values = {
        "BOXIE_IMAGE": os.environ["BOXIE_IMAGE"],
        "BOXIE_DATA_DIR": "/srv/sanctuary/boxie",
        "BOXIE_API_CONFIG": str(credentials / "api.json"),
        "BOXIE_SUPERVISOR_CONFIG": str(credentials / "supervisor.json"),
        "BOXIE_PROFILES_FILE": str(credentials / "profiles.json"),
        "BOXIE_SUPERVISOR_CREDENTIAL_FILE": str(credentials / "supervisor.secret"),
        "BOXIE_CONSUMER_CREDENTIAL_FILE": str(credentials / "consumer.secret"),
        "BOXIE_POSTGRES_DSN_FILE": str(credentials / "postgres-dsn.secret"),
        "BOXIE_TEMPORAL_CA_FILE": str(tls / "api/frontend-ca.pem"),
        "BOXIE_API_TEMPORAL_CERT_FILE": str(tls / "api/boxie-api.pem"),
        "BOXIE_API_TEMPORAL_KEY_FILE": str(tls / "api/boxie-api.key"),
        "BOXIE_SUPERVISOR_TEMPORAL_CERT_FILE": str(tls / "supervisor/boxie-supervisor.pem"),
        "BOXIE_SUPERVISOR_TEMPORAL_KEY_FILE": str(tls / "supervisor/boxie-supervisor.key"),
        "BOXIE_CONTROL_NETWORK": "boxie-control",
        "BOXIE_CONSUMER_NETWORK": "boxie-consumers",
        "TEMPORAL_CERTS_DIR": str(tls / "server"),
        "TEMPORAL_OPERATOR_CERTS_DIR": str(tls / "operator"),
        "TEMPORAL_UI_CERTS_DIR": str(tls / "ui"),
        "BOXIE_HOST_ID": secret("host-id"),
        "BOXIE_INSTALLATION_ID": secret("installation-id"),
        "BOXIE_TEMPORAL_NAMESPACE": "boxie",
        "OBS_COLLECTOR_IMAGE": os.environ["OBS_COLLECTOR_IMAGE"],
        "OBS_JOURNAL_GROUP_GID": os.environ["OBS_JOURNAL_GROUP_GID"],
        "OBS_GRAFANA_HOSTNAME": os.environ["OPERATOR_GRAFANA_HOSTNAME"],
        "OBS_GRAFANA_PLUGIN_DIR": str(root / "grafana-plugins"),
        "OBS_GRAFANA_ADMIN_PASSWORD_FILE": str(root / "grafana-admin"),
        "OBS_PROMETHEUS_CONFIG_FILE": str(root / "prometheus.yml"),
        "OPERATOR_CONFIG_FILE": str(root / "cloudflared.yml"),
        "OPERATOR_CREDENTIALS_FILE": str(root / "tunnel.json"),
    }
    for variable, name in (
        ("POSTGRES_PASSWORD", "postgres-password"),
        ("BOXIE_DB_PASSWORD", "boxie-password"),
        ("TEMPORAL_DB_PASSWORD", "temporal-password"),
        ("VISIBILITY_DB_PASSWORD", "visibility-password"),
    ):
        values[variable] = secret(name)
    write_environment(root / "boxie.env", values)

    infra = source / "packages/boxie/infra"
    _render_template(
        infra / "observability/prometheus.yml",
        root,
        values,
        "BOXIE_INSTALLATION_ID",
        "BOXIE_HOST_ID",
        "BOXIE_TEMPORAL_NAMESPACE",
    )
    _render_template(
        infra / "ingress/cloudflared.yml",
        root,
        os.environ,
        "OPERATOR_TUNNEL_ID",
        "OPERATOR_TEAM_NAME",
        "OPERATOR_GRAFANA_HOSTNAME",
        "OPERATOR_TEMPORAL_HOSTNAME",
        "OPERATOR_GRAFANA_AUDIENCE",
        "OPERATOR_TEMPORAL_AUDIENCE",
    )
    update_profile(root, infra)


def update_profile(root: Path, source: Path) -> None:
    profiles_path = root / "boxie/profiles.json"
    profiles = json.loads(profiles_path.read_text()) if profiles_path.exists() else {}
    profile = profiles.get("default")
    if profile is None:
        profile = json.loads((source / "profiles/default.json").read_text())["default"]
    profile["image_digest"] = os.environ["BOXIE_SANDBOX_IMAGE"]
    profiles["default"] = profile
    _replace_private_text(profiles_path, json.dumps(profiles, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--profile-only", action="store_true")
    args = parser.parse_args()
    root = Path(os.environ.get("SANCTUARY_CONFIG_DIR", "/etc/sanctuary"))
    if args.profile_only:
        update_profile(root, args.source)
    else:
        render(root, args.source)


if __name__ == "__main__":
    main()
