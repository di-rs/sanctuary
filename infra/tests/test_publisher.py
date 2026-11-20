import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from infra.control.bucket import Bucket
from infra.control.publish import main
from infra.control.release import Release

HEAD = "a" * 40
DIGEST = hashlib.sha256(b"private bundle").hexdigest()


@pytest.fixture
def delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Mock:
    env = {
        "GITHUB_REPOSITORY": "org/app",
        "GITHUB_RUN_ID": "11",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_OUTPUT": str(tmp_path / "out"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        "PREVIEW_ZONE": "example.net",
        "BUILT_HEAD": HEAD,
        "BUILT_DIGEST": DIGEST,
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    bucket = Mock(spec=Bucket)
    monkeypatch.setattr("infra.control.publish.Bucket", lambda: bucket)
    return bucket


def test_closed_while_uploading_cannot_reactivate_preview(
    delivery: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["publish", "finish", "pr-7"])
    delivery.get.side_effect = lambda _, path, __: path.write_bytes(b"private bundle")
    with patch(
        "infra.control.publish.eligible", side_effect=[(True, HEAD, HEAD), (False, HEAD, HEAD)]
    ):
        main()
    delivery.put.assert_not_called()
    assert ("delete-object", "--key", "desired/pr-7.json") in [
        v.args for v in delivery.api.call_args_list
    ]


def test_changed_staging_bytes_cannot_become_release(
    delivery: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["publish", "finish", "pr-7"])
    delivery.get.side_effect = lambda _, path, __: path.write_bytes(b"wrong")
    with (
        patch("infra.control.publish.eligible", return_value=(True, HEAD, HEAD)),
        pytest.raises(ValueError, match="digest"),
    ):
        main()
    delivery.put.assert_not_called()


@pytest.mark.parametrize("action", ["release", "rollback"])
def test_republish_reuses_exact_historical_record(
    action: str, delivery: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RELEASE_COMMIT", HEAD)
    monkeypatch.setattr(sys, "argv", ["publish", action, "boxie"])
    record = Release("boxie", HEAD, {"boxie": DIGEST, "sandbox": "e" * 64})
    delivery.names.return_value = [f"history/boxie/{HEAD}.json"]
    delivery.get.side_effect = lambda _, path, __: path.write_bytes(record.encode())
    results = {}

    def write(key: str, path: Path) -> None:
        results[key] = json.loads(path.read_bytes())

    delivery.put.side_effect = write
    main()
    assert results == {"desired/boxie.json": json.loads(record.encode())}
    delivery.publish_blob.assert_not_called()
