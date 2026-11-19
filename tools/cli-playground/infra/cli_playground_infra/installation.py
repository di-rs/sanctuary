"""Render private cli-playground settings and its own preview credential."""

import argparse
import os
import secrets
import tempfile
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


def _ensure_private_credential(path: Path, error_message: str) -> None:
    if not path.exists():
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(secrets.token_hex(32) + "\n")
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError(error_message)


def render(root: Path) -> None:
    credentials = root / "boxie"
    product = root / "cli-playground"
    product.mkdir(mode=0o700, exist_ok=True)

    token = product / "preview-token"
    token_error = "Preview credential must be a private nonempty regular file"
    _ensure_private_credential(token, token_error)
    if not token.read_text().strip():
        raise ValueError(token_error)

    password_file = product / "postgres-password"
    _ensure_private_credential(
        password_file, "PostgreSQL credential must be a private regular file"
    )
    password = password_file.read_text().strip()
    if len(password) != 64 or any(char not in "0123456789abcdef" for char in password):
        raise ValueError("Invalid Playground PostgreSQL password")
    url_file = product / "database-url.secret"
    # Replace rather than follow a stale symlink when rendering credentials.
    _replace_private_text(
        url_file, f"postgresql+psycopg://cli_playground:{password}@postgres/cli_playground\n"
    )

    write_environment(
        root / "cli-playground.env",
        {
            "CLI_PLAYGROUND_DATABASE_URL_FILE": str(url_file),
            "CLI_PLAYGROUND_DATABASE_NETWORK": "boxie-postgres_playground",
            "CLI_PLAYGROUND_IMAGE": os.environ["CLI_PLAYGROUND_IMAGE"],
            "CLI_PLAYGROUND_DOMAIN": os.environ["CLI_PLAYGROUND_DOMAIN"],
            "CLI_PLAYGROUND_DEPLOY_TOKEN": token.read_text().strip(),
            "CLI_PLAYGROUND_BOXIE_URL": "http://boxie-api:8090",
            "CLI_PLAYGROUND_BOXIE_CREDENTIAL_FILE": str(credentials / "consumer.secret"),
            "CLI_PLAYGROUND_CONSUMER_NETWORK": "boxie-consumers",
            "CLI_PLAYGROUND_PROXY_NETWORK": "cli-playground-proxy",
            "CLI_PLAYGROUND_DATA_VOLUME": "cli-playground-data",
            "CLI_PLAYGROUND_CERTIFICATES_VOLUME": "cli-playground-certificates",
            "ACME_EMAIL": os.environ["ACME_EMAIL"],
            "CLOUDFLARE_DNS_API_TOKEN": os.environ["CLOUDFLARE_DNS_API_TOKEN"],
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    root = Path(os.environ.get("SANCTUARY_CONFIG_DIR", "/etc/sanctuary"))
    render(root)


if __name__ == "__main__":
    main()
