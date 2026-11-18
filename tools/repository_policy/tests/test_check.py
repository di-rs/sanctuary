import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from repository_policy import check

APP_ID = 15368
REPOSITORY_ENDPOINT = "repos/di-rs/sanctuary"
RULES_ENDPOINT = f"{REPOSITORY_ENDPOINT}/rules/branches/release%2Fmain?per_page=100"


def pull_request(*methods: str) -> dict[str, object]:
    return {"type": "pull_request", "parameters": {"allowed_merge_methods": methods}}


def required_checks(**contexts: int | None) -> dict[str, object]:
    return {
        "type": "required_status_checks",
        "parameters": {
            "required_status_checks": [
                {"context": context, "integration_id": app} for context, app in contexts.items()
            ],
        },
    }


@pytest.fixture(autouse=True)
def checked_in_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ruleset = tmp_path / "ruleset.json"
    ruleset.write_text(
        json.dumps(
            {
                "target": "branch",
                "enforcement": "active",
                "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
                "rules": [
                    pull_request("squash"),
                    required_checks(Validation=APP_ID, Policy=APP_ID),
                ],
            }
        )
    )
    monkeypatch.setattr(check, "RULESET", ruleset)
    return ruleset


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    def respond(*pages: list[object], merge_enabled: bool = False) -> None:
        def fake_run(
            command: list[str], *, capture_output: bool, check: bool, timeout: int
        ) -> subprocess.CompletedProcess[bytes]:
            assert command[:6] == ["gh", "api", "--hostname", "github.com", "--method", "GET"]
            assert capture_output and check and timeout > 0
            if command[6:] == [REPOSITORY_ENDPOINT]:
                payload: object = {
                    "default_branch": "release/main",
                    "allow_merge_commit": merge_enabled,
                    "allow_rebase_merge": False,
                    "allow_squash_merge": True,
                }
            else:
                assert command[6:] == [RULES_ENDPOINT, "--paginate", "--slurp"]
                payload = pages
            return subprocess.CompletedProcess(command, 0, json.dumps(payload).encode(), b"")

        monkeypatch.setattr(subprocess, "run", fake_run)

    return respond


def test_matches_across_active_rules_and_pages(
    github: Callable[..., None], capsys: pytest.CaptureFixture[str]
) -> None:
    github(
        [pull_request("merge", "squash"), required_checks(Policy=APP_ID), {"type": "deletion"}],
        [required_checks(Validation=APP_ID, Policy=APP_ID), pull_request("squash")],
    )

    assert check.main([]) == 0
    result = capsys.readouterr()
    assert result.out == "Merge policy matches for di-rs/sanctuary default branch 'release/main'\n"
    assert not result.err


def test_reports_context_and_app_drift_at_both_merge_layers(
    github: Callable[..., None], capsys: pytest.CaptureFixture[str]
) -> None:
    github(
        [pull_request("squash", "merge", "rebase"), required_checks(Policy=None, Other=42)],
        merge_enabled=True,
    )

    assert check.main([]) == 1
    result = capsys.readouterr()
    assert result.out.splitlines()[1:] == [
        "- Missing required check 'Policy' (app 15368)",
        "- Missing required check 'Validation' (app 15368)",
        "- Unexpected required check 'Other' (app 42)",
        "- Unexpected required check 'Policy' (any app)",
        "- Active ruleset merge methods are merge, rebase, squash (expected squash)",
        "- Repository merge methods are merge, squash (expected squash)",
    ]
    assert not result.err


def test_reports_repository_drift_even_when_ruleset_limits_merges(
    github: Callable[..., None], capsys: pytest.CaptureFixture[str]
) -> None:
    github(
        [pull_request("squash"), required_checks(Validation=APP_ID, Policy=APP_ID)],
        merge_enabled=True,
    )

    assert check.main([]) == 1
    assert capsys.readouterr().out.splitlines()[1:] == [
        "- Repository merge methods are merge, squash (expected squash)"
    ]


def test_reports_missing_active_rules(
    github: Callable[..., None], capsys: pytest.CaptureFixture[str]
) -> None:
    github([])

    assert check.main([]) == 1
    output = capsys.readouterr().out
    assert "Missing required check 'Policy' (app 15368)" in output
    assert "No active pull request rule applies to the default branch" in output


def test_malformed_live_rules_are_an_observation_failure(
    github: Callable[..., None], capsys: pytest.CaptureFixture[str]
) -> None:
    github([{"type": "required_status_checks", "parameters": {}}])

    assert check.main([]) == 2
    result = capsys.readouterr()
    assert not result.out
    assert "Invalid required_status_checks in GitHub default-branch rules" in result.err


def test_unreadable_policy_is_an_observation_failure(
    checked_in_policy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    checked_in_policy.unlink()

    assert check.main([]) == 2
    result = capsys.readouterr()
    assert not result.out
    assert "Cannot compare merge policy" in result.err


def test_failed_request_does_not_expose_gh_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failed_run(
        command: list[str], *, capture_output: bool, check: bool, timeout: int
    ) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.CalledProcessError(1, command, stderr=b"untrusted raw diagnostic")

    monkeypatch.setattr(subprocess, "run", failed_run)

    assert check.main([]) == 2
    result = capsys.readouterr()
    assert not result.out
    assert "GitHub GET repos/di-rs/sanctuary failed" in result.err
    assert "untrusted raw diagnostic" not in result.err
