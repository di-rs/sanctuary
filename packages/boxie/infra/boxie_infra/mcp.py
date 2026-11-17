"""Provision a private Viewer token for the Grafana MCP adapter."""

import base64
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ACCOUNT = "sanctuary-mcp"
TOKEN = "sanctuary-mcp-read"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise RuntimeError("Grafana redirected a credential-bearing request")


def provision(url: str, password_file: Path, token_file: Path) -> None:
    password = password_file.read_text().strip()
    authorization = "Basic " + base64.b64encode(f"admin:{password}".encode()).decode()
    opener = build_opener(ProxyHandler({}), NoRedirect)

    def request(path: str, data: object = None, bearer: str | None = None) -> Any:
        req = Request(
            url + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={
                "Authorization": f"Bearer {bearer}" if bearer else authorization,
                "Content-Type": "application/json",
            },
        )
        with opener.open(req, timeout=20) as response:
            return json.load(response)

    accounts = request(f"/api/serviceaccounts/search?query={ACCOUNT}&perpage=100")
    matches = [item for item in accounts["serviceAccounts"] if item["name"] == ACCOUNT]
    if len(matches) > 1:
        raise RuntimeError("Duplicate MCP service accounts; inspect Grafana")
    if matches:
        account = matches[0]
    else:
        if token_file.exists():
            raise RuntimeError("MCP token exists without its service account; inspect Grafana")
        account = request("/api/serviceaccounts", {"name": ACCOUNT, "role": "Viewer"})
    if account["role"] != "Viewer" or account.get("isDisabled", False):
        raise RuntimeError("MCP service account must be an enabled Viewer")
    account_id = int(account["id"])
    if token_file.exists():
        if token_file.is_symlink() or token_file.stat().st_mode & 0o077:
            raise RuntimeError("MCP token file must be private and not a symlink")
        token = token_file.read_text().strip()
        if not token:
            raise RuntimeError("MCP token file is empty")
        identity = request("/api/user", bearer=token)
        if identity["login"] != account["login"] or identity.get("isGrafanaAdmin", False):
            raise RuntimeError("Stored token does not belong to the MCP Viewer")
        return
    tokens = request(f"/api/serviceaccounts/{account_id}/tokens")
    if any(item["name"] == TOKEN for item in tokens):
        raise RuntimeError("MCP token exists in Grafana but not on disk; revoke it before retrying")
    token = request(f"/api/serviceaccounts/{account_id}/tokens", {"name": TOKEN})["key"]
    # Exclusive creation prevents silently replacing credentials on retries.
    descriptor = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(token + "\n")
        output.flush()
        os.fsync(output.fileno())


def main() -> None:
    try:
        provision(
            "http://grafana:3000", Path("/admin-password"), Path("/credentials/grafana-token")
        )
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError, KeyError, HTTPError, URLError) as error:
        # Do not print remote response bodies, passwords, or token material.
        print(f"Grafana MCP provisioning failed ({type(error).__name__}).", file=sys.stderr)
        raise SystemExit(1) from None
    print("Grafana MCP Viewer credential ready.")


if __name__ == "__main__":
    main()
