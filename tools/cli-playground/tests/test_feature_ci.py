"""Feature controller reconciles current PR state before touching a host."""

import subprocess
from unittest.mock import MagicMock

import feature_ci
import pytest

REPO = "di-rs/sanctuary"
SHA = "a" * 40


@pytest.mark.parametrize(
    "state,base,files,prior,expected",
    [
        ("open", "master", "tools/cli-playground/frontend/src/app.ts", None, ("deploy", None)),
        (
            "open",
            "master",
            "tools/cli-playground/src/cli_playground/routes.py",
            None,
            ("deploy", None),
        ),
        ("open", "master", "tools/cli-playground/docs/previews.md", None, ("skip", None)),
        ("open", "master", "buildins/echor/src/main.rs", "success", ("remove", 17)),
        ("closed", "master", "", "failure", ("remove", 17)),
        ("closed", "master", "", "inactive", ("skip", None)),
        ("open", "release", "", "success", ("remove", 17)),
    ],
)
def test_select_current_pr(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    base: str,
    files: str,
    prior: str | None,
    expected: tuple[str, int | None],
) -> None:
    def api(path: str) -> object:
        if path.endswith("/pulls/11"):
            return {"head": {"sha": SHA}, "state": state, "base": {"ref": base}, "changed_files": 1}
        if "/statuses?" in path:
            return [{"state": prior}]
        assert "environment=cli-playground%2Ffeature-pr-11" in path
        return [{"id": 17}] if prior else []

    monkeypatch.setattr(feature_ci, "api", api)
    file_list = MagicMock(return_value=files)
    monkeypatch.setattr(subprocess, "check_output", file_list)
    assert feature_ci.selection(REPO, 11, SHA) == expected
    if state == "open" and base == "master":
        args = file_list.call_args.args[0]
        assert "--paginate" in args and "previous_filename" in args[-1]
    else:
        file_list.assert_not_called()


def test_stale_event_never_removes_or_deploys(monkeypatch: pytest.MonkeyPatch) -> None:
    github = MagicMock(return_value={"head": {"sha": "b" * 40}})
    monkeypatch.setattr(feature_ci, "api", github)
    assert feature_ci.selection(REPO, 11, SHA) == ("skip", None)
    github.assert_called_once()
