"""Execute inside a trusted gateway. Its deployment token stays in the container."""

import argparse
import http.client
import os
import sys
from urllib.parse import urlsplit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("upload", "renew", "close", "health"))
    parser.add_argument("number", type=int)
    parser.add_argument("sha")
    parser.add_argument("length", type=int, nargs="?", default=0)
    args = parser.parse_args()
    routes = {
        "upload": ("POST", f"/api/environments?pr={args.number}&sha={args.sha}"),
        "renew": ("POST", f"/api/deployments/{args.number}/renew?sha={args.sha}"),
        "close": ("DELETE", f"/api/pull-requests/{args.number}?drain=true"),
        "health": ("GET", "/healthz"),
    }
    method, path = routes[args.operation]
    headers = {
        "Host": str(urlsplit(os.environ["CLI_PLAYGROUND_PUBLIC_URL"]).netloc),
        "Authorization": "Bearer " + os.environ["CLI_PLAYGROUND_DEPLOY_TOKEN"],
        "Content-Length": str(args.length),
        "Content-Type": "application/zip",
    }
    connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=180)
    try:
        connection.request(method, path, sys.stdin.buffer if args.length else None, headers)
        response = connection.getresponse()
        if response.status not in (200, 201, 204):
            raise SystemExit(f"Playground {args.operation} returned HTTP {response.status}")
        response.read(65536)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
