"""Publisher policies exercised through real SDK requests and HTTP streams."""

import gzip
import json
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
from pathlib import Path
from threading import Thread
from types import ModuleType

import anyio
import github_publication
import httpx
import pytest
from conftest import BASE, REPO, SHA
from githubkit import GitHub

TOOLS = Path(__file__).resolve().parents[2]
PREVIEW = TOOLS / "cli-playground/preview_ci.py"
REPORT = TOOLS / "cli-bench/report.py"


@pytest.fixture(params=[REPORT, PREVIEW], ids=["report", "preview"])
def publisher(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    script: Path = request.param
    monkeypatch.syspath_prepend(str(script.parent))
    return import_module(script.stem)


class Body(httpx.AsyncByteStream):
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        if self.mode == "compressed":
            yield gzip.compress(b"x" * 1000000)
        elif self.mode == "trickle":
            for _ in range(100):
                yield b"x"
                await anyio.sleep(0.01)
        else:
            yield b"x" * (17 if self.mode == "oversized" else 16)

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize("status", [200, 500])
@pytest.mark.parametrize("mode", ["oversized", "exact-limit", "trickle"])
def test_response_limits_deadlines_and_cleanup(
    publisher: ModuleType, mode: str, status: int
) -> None:
    body = Body(mode)
    api = GitHub(
        "test-token",
        async_transport=httpx.MockTransport(lambda request: httpx.Response(status, stream=body)),
    )
    started = time.monotonic()
    if mode == "exact-limit" and status == 200:
        assert publisher.github_request(api, "user", limit=16, timeout=0.08) == b"x" * 16
    else:
        with pytest.raises(ValueError):
            publisher.github_request(api, "user", limit=16, timeout=0.08)
    assert time.monotonic() - started < 0.7
    assert body.closed


def test_redirected_artifact_does_not_forward_credentials(publisher: ModuleType) -> None:
    authorizations: list[str | None] = []

    def handle(request: httpx.Request) -> httpx.Response:
        authorizations.append(request.headers.get("authorization"))
        if request.url.host == "api.github.com":
            return httpx.Response(302, headers={"location": "https://artifacts.example/archive"})
        return httpx.Response(200, content=b"archive")

    api = GitHub("test-token", async_transport=httpx.MockTransport(handle))
    assert publisher.github_request(api, "repos/owner/name/actions/artifacts/1/zip") == b"archive"
    assert authorizations == ["token test-token", None]


def test_pagination_retains_filters_and_fails_on_exhaustion(
    publisher: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queries: list[dict[str, str]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        queries.append(dict(request.url.params))
        return httpx.Response(200, json=[{"id": i} for i in range(100)])

    monkeypatch.setattr(github_publication, "MAX_PAGES", 2)
    api = GitHub("test-token", async_transport=httpx.MockTransport(handle))
    with pytest.raises(ValueError, match="pagination limit"):
        publisher.github_pages(
            api, "repos/owner/name/deployments?environment=cli-playground%2Fpr-7"
        )
    assert queries == [
        {"environment": "cli-playground/pr-7", "per_page": "100", "page": str(i)} for i in (1, 2)
    ]


def test_sdk_retries_and_caching_are_disabled_for_state_checks(publisher: ModuleType) -> None:
    requests: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request.method)
        return httpx.Response(500, json={"message": "failed"})

    api = GitHub("test-token", async_transport=httpx.MockTransport(handle))
    for _ in range(2):
        with pytest.raises(ValueError):
            publisher.github_request(
                api, "repos/owner/name/issues/1/comments", method="POST", body={"body": "test"}
            )
    assert requests == ["POST", "POST"]


def test_actual_http_stream_has_total_deadline(publisher: ModuleType) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", "1000")
            self.end_headers()
            try:
                for _ in range(1000):
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    time.sleep(0.01)
            except BrokenPipeError, ConnectionResetError:
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        api = GitHub(
            "test-token", base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False
        )
        started = time.monotonic()
        with pytest.raises(ValueError):
            publisher.github_request(api, "user", timeout=0.08)
        assert time.monotonic() - started < 0.7
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_token_environment_precedence(
    publisher: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "preferred")
    monkeypatch.setenv("GITHUB_TOKEN", "fallback")
    assert publisher.github_client().auth.token == "preferred"
    monkeypatch.delenv("GH_TOKEN")
    assert publisher.github_client().auth.token == "fallback"


@pytest.mark.parametrize("status", [200, 302, 500])
def test_unexpected_compression_is_rejected_before_buffering(
    publisher: ModuleType, status: int
) -> None:
    body = Body("compressed")
    response = httpx.Response(status, headers={"content-encoding": "gzip"}, stream=body)

    def handle(request: httpx.Request) -> httpx.Response:
        return response

    api = GitHub("test-token", async_transport=httpx.MockTransport(handle))
    with pytest.raises(ValueError):
        publisher.github_request(api, "user", limit=2048)
    assert response.num_bytes_downloaded == 0
    assert body.closed


@pytest.mark.parametrize("phase", ["read", "close"])
@pytest.mark.parametrize("failure", [httpx.ReadError, httpx.ReadTimeout, httpx.RemoteProtocolError])
def test_stream_transport_failures_are_sanitized(
    publisher: ModuleType, phase: str, failure: type[httpx.HTTPError]
) -> None:
    class BrokenBody(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"partial response"
            if phase == "read":
                raise failure("sensitive signed artifact URL")

        async def aclose(self) -> None:
            self.closed = True
            if phase == "close":
                raise failure("sensitive signed artifact URL")

    body = BrokenBody()
    api = GitHub(
        "test-token",
        async_transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body)),
    )
    with pytest.raises(ValueError) as caught:
        publisher.github_request(api, "repos/owner/name/actions/artifacts/1/zip")
    assert "sensitive signed artifact URL" not in str(caught.value)
    assert caught.value.__cause__ is not None
    assert body.closed


@pytest.mark.parametrize("kind", ["preview", "bench", "size"])
@pytest.mark.parametrize("scenario", ["current", "stale", "timeout", "upstream-error"])
def test_publisher_script_from_another_directory(tmp_path: Path, kind: str, scenario: str) -> None:
    workflow_name = f"cli-{'playground' if kind == 'preview' else kind}.yml"
    workflow_path = f".github/workflows/{workflow_name}"
    run_path = f"/{BASE}/actions/runs/500"
    pull_path = f"/{BASE}/pulls/7"
    comments_path = f"/{BASE}/issues/7/comments"
    upstream_detail = "fixture private upstream detail"
    responses: dict[str, object] = {
        f"GET {run_path}": {
            "id": 500,
            "run_number": 10,
            "run_attempt": 1,
            "workflow_id": 42,
            "event": "pull_request",
            "status": "completed",
            "conclusion": "success",
            "path": workflow_path,
            "repository": {"full_name": REPO},
            "head_sha": SHA,
            "pull_requests": [{"number": 7}],
        },
        f"GET /{BASE}/actions/workflows/{workflow_name}": {"id": 42, "path": workflow_path},
        f"GET {pull_path}": {
            "number": 7,
            "state": "open",
            "head": {"sha": "b" * 40 if scenario == "stale" else SHA},
            "base": {"ref": "master", "repo": {"full_name": REPO}},
        },
    }
    if scenario == "current":
        responses.update(
            {
                f"GET {run_path}/artifacts?per_page=100&page=1": {"artifacts": []},
                f"GET {comments_path}?per_page=100&page=1": [],
                f"POST {comments_path}": {},
            }
        )
        if kind != "preview":
            job_name = (
                "⏱️ Run CLI benchmarks (ubuntu-24.04)"
                if kind == "bench"
                else "📦 Measure Linux binary sizes"
            )
            responses[f"GET {run_path}/attempts/1/jobs?per_page=100&page=1"] = {
                "jobs": [{"name": job_name, "conclusion": "success"}]
            }

    # Install a test-only HTTP transport at Python startup so the actual script
    # resolves its imports and runs its CLI with a foreign cwd and synthetic credentials.
    (tmp_path / "fixture.json").write_text(
        json.dumps({"responses": responses, "scenario": scenario, "detail": upstream_detail}),
        encoding="utf-8",
    )
    (tmp_path / "sitecustomize.py").write_text(
        """\
import json
from pathlib import Path

import githubkit
import httpx

fixture = json.loads(Path("fixture.json").read_text(encoding="utf-8"))

def respond(request):
    assert request.url.host == "api.github.com"
    assert request.headers["Authorization"] == "token publisher-fixture-token"
    key = f"{request.method} {request.url.raw_path.decode()}"
    with Path("requests.log").open("a", encoding="utf-8") as log:
        print(key, file=log)
    assert key in fixture["responses"], key
    if fixture["scenario"] == "timeout":
        raise httpx.ReadTimeout(fixture["detail"], request=request)
    if fixture["scenario"] == "upstream-error":
        return httpx.Response(500, json={"message": fixture["detail"]})
    return httpx.Response(200, json=fixture["responses"][key])

class FixtureGitHub(githubkit.GitHub):
    def __init__(self, *args, **kwargs):
        if "config" not in kwargs:
            kwargs["async_transport"] = httpx.MockTransport(respond)
        super().__init__(*args, **kwargs)

githubkit.GitHub = FixtureGitHub
""",
        encoding="utf-8",
    )
    args = (
        [str(PREVIEW), "publish"] if kind == "preview" else [str(REPORT), "--kind", kind, "--post"]
    )
    result = subprocess.run(
        [sys.executable, *args, "--repo", REPO, "--run-id", "500"],
        cwd=tmp_path,
        env={
            "GH_TOKEN": "publisher-fixture-token",
            "GITHUB_ACTIONS": "true",
            "PYTHONPATH": str(tmp_path),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    output = result.stdout + result.stderr
    assert upstream_detail not in output
    assert "publisher-fixture-token" not in output
    assert "Traceback" not in result.stderr
    requests = (tmp_path / "requests.log").read_text(encoding="utf-8").splitlines()
    if scenario == "current":
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        heading = {
            "preview": "### cli-playground",
            "bench": "### CLI benchmarks",
            "size": "### Package binary sizes",
        }[kind]
        assert heading in result.stdout
        assert set(requests) == responses.keys()
        assert requests[-1] == f"POST {comments_path}"
    elif scenario == "stale":
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        assert result.stdout == (
            "" if kind == "preview" else "Skipped: no current eligible PR report.\n"
        )
        assert requests == list(responses)
    else:
        assert result.returncode == 1
        assert result.stdout == ""
        if kind == "preview":
            assert result.stderr == (
                "cli-playground CI failed; check configuration, build logs, and artifact validity.\n"
            )
        else:
            assert result.stderr == (
                f"Cannot report {'benchmarks' if kind == 'bench' else 'sizes'}: "
                "GitHub request failed or exceeded its response limit or deadline\n"
            )
        assert requests == [f"GET {run_path}"]
