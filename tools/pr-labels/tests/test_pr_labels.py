"""Exercise contributor selections and metadata-only GitHub reconciliation."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from pr_labels import (
    AUTO,
    MANUAL,
    ROOT,
    GitHub,
    areas,
    catalog,
    classify,
    desired_labels,
    reconcile,
    sync,
)

ENTRIES = catalog(ROOT / ".github/labels.yml")
TEMPLATE = (ROOT / ".github/pull_request_template.md").read_text()


def body(*choices: str) -> str:
    text = TEMPLATE
    for choice in choices:
        text = text.replace(f"- [ ] `{choice}`", f"- [x] `{choice}`")
    return text


def pr(**updates: Any) -> dict[str, Any]:
    result = dict(
        number=42,
        state="open",
        draft=False,
        changed_files=1,
        head={"sha": "head"},
        base={"sha": "base", "ref": "feature/parent"},
        body=body("type:fix", "risk:low", "impact:none"),
        labels=[{"name": name} for name in [AUTO, "run-ci", "custom"]],
    )
    result.update(updates)
    return result


def test_template_requires_explicit_selections() -> None:
    assert len(classify(TEMPLATE, ENTRIES).errors) == 3
    selected = classify(
        body("type:fix", "risk:high", "impact:persistence", "impact:security"), ENTRIES
    )
    assert not selected.errors
    assert selected.labels == {"type:fix", "risk:high", "impact:persistence", "impact:security"}


@pytest.mark.parametrize(
    "choices",
    [
        ("type:fix", "type:feature", "risk:low", "impact:none"),
        ("type:fix", "risk:low", "risk:medium", "impact:none"),
        ("type:fix", "risk:low", "impact:none", "impact:breaking"),
    ],
)
def test_conflicting_selections_do_not_assign_family(choices: tuple[str, ...]) -> None:
    result = classify(body(*choices), ENTRIES)
    assert result.errors
    for error in result.errors:
        family = error.split()[2]
        assert not any(label.startswith(family + ":") for label in result.labels)


@pytest.mark.parametrize(
    "extra",
    [
        "- [x] `auto-merge-candidate`",
        "- [x] `risk:unknown`",
        "- [x] low",
        "- [x] `risk:low`",
    ],
)
def test_untrusted_or_duplicate_choices(extra: str) -> None:
    text = body("type:fix", "risk:low", "impact:none").replace(
        "<!-- /labels:risk -->", extra + "\n<!-- /labels:risk -->"
    )
    assert classify(text, ENTRIES).errors


def test_free_prose_does_not_set_labels_or_execute(tmp_path: Path) -> None:
    target = tmp_path / "injected"
    text = body("type:docs", "risk:low", "impact:none") + f"\n- [x] `risk:high`\n$(touch {target})"
    assert classify(text, ENTRIES).labels == {"type:docs", "risk:low"}
    assert not target.exists()
    assert classify(text + "\n<!-- labels:type -->", ENTRIES).errors


def test_overlapping_paths_and_renames_include_old_and_new_areas() -> None:
    files = [
        {"filename": "packages/boxie/infra/docs/deploy.md"},
        {
            "filename": "tools/cli-check/src/check.py",
            "previous_filename": "utils/cli-testing/src/lib.rs",
        },
        {"filename": "buildins/catr/src/main.rs", "status": "removed"},
        {"filename": "Cargo.lock"},
        {"filename": ".github/workflows/check.yml"},
    ]
    assert areas(files, ENTRIES) == {
        "area:boxie",
        "area:infrastructure",
        "area:docs",
        "area:repo-tooling",
        "area:shared-libraries",
        "area:builtins",
        "area:workspace",
        "area:ci",
    }


@pytest.mark.parametrize(
    "event,updates,authorized",
    [
        ({"action": "synchronize"}, {}, True),
        ({"action": "reopened"}, {}, True),
        ({"action": "edited", "changes": {"base": {}}}, {}, True),
        ({}, {"draft": True}, True),
        ({}, {"body": body("type:fix", "risk:medium", "impact:none")}, True),
        ({}, {"body": TEMPLATE}, True),
        ({}, {}, False),
    ],
)
def test_candidate_revocation(
    event: dict[str, Any], updates: dict[str, Any], authorized: bool
) -> None:
    desired, _ = desired_labels(
        pr(**updates),
        [{"filename": "packages/kara/src/main.rs"}],
        ENTRIES,
        event,
        authorized_candidate=authorized,
    )
    assert AUTO not in desired and MANUAL in desired
    assert {"run-ci", "custom", "area:kara"} <= desired


def test_evidence_edit_invalidates_candidate() -> None:
    current = pr()
    event = {
        "action": "edited",
        "changes": {"body": {"from": current["body"] + "\nold evidence"}},
        "pull_request": current,
    }
    desired, _ = desired_labels(current, [], ENTRIES, event, authorized_candidate=True)
    assert AUTO not in desired


def test_low_risk_does_not_grant_candidate_and_backfill_revokes_old_candidate() -> None:
    for current, backfill in [(pr(labels=[]), False), (pr(), True)]:
        desired, _ = desired_labels(
            current, [], ENTRIES, {}, authorized_candidate=True, backfill=backfill
        )
        assert AUTO not in desired and MANUAL in desired
    desired, _ = desired_labels(pr(), [], ENTRIES, {}, authorized_candidate=True)
    assert AUTO in desired and MANUAL not in desired


class FakeGitHub(GitHub):
    def __init__(self, current: dict[str, Any] | None = None) -> None:
        super().__init__("owner/repo", "unused")
        self.current = current or pr()
        self.files = [{"filename": "packages/kara/README.md"}]
        self.writes: list[tuple[str, str, object]] = []
        self.permission = "write"
        self.existing: list[dict[str, Any]] = []

    def request(self, method: str, path: str, data: object = None) -> Any:
        if method == "GET":
            if path.startswith("collaborators/"):
                return {"permission": self.permission}
            if path == "pulls/42":
                return copy.deepcopy(self.current)
            if path.startswith("pulls/42/files?"):
                return self.files
            if path.startswith("labels?"):
                return self.existing
            raise AssertionError(path)
        self.writes.append((method, path, data))
        if method == "DELETE":
            import urllib.parse

            label = urllib.parse.unquote(path.rsplit("/", 1)[1])
            self.current["labels"] = [
                item for item in self.current["labels"] if item["name"] != label
            ]
        elif method == "POST" and path == "issues/42/labels":
            assert isinstance(data, dict)
            self.current["labels"].extend({"name": name} for name in data["labels"])
        return {}


def test_reconcile_dry_run_apply_and_idempotence() -> None:
    api = FakeGitHub()
    planned = reconcile(api, 42, ENTRIES, {"action": "synchronize"}, apply=False)
    assert not api.writes
    assert planned["remove"] == [AUTO]
    assert {"area:kara", "area:docs", MANUAL} <= set(planned["add"])
    applied = reconcile(api, 42, ENTRIES, {"action": "synchronize"}, apply=True)
    assert applied["add"] == planned["add"]
    api.writes.clear()
    reconcile(api, 42, ENTRIES, {}, apply=True)
    assert not api.writes
    assert {"run-ci", "custom"} <= {label["name"] for label in api.current["labels"]}


def test_partial_file_listing_fails_without_mutation() -> None:
    api = FakeGitHub(pr(changed_files=3001))
    with pytest.raises(ValueError, match="incomplete"):
        reconcile(api, 42, ENTRIES, {}, apply=True)
    assert not api.writes


def test_closed_pr_is_not_modified() -> None:
    api = FakeGitHub(pr(state="closed"))
    assert reconcile(api, 42, ENTRIES, {}, apply=True)["skipped"] == "closed"
    assert not api.writes


@pytest.mark.parametrize("permission", ["read", "triage"])
def test_only_write_or_higher_can_add_candidate(permission: str) -> None:
    api = FakeGitHub()
    api.permission = permission
    event = {
        "action": "labeled",
        "label": {"name": AUTO},
        "sender": {"login": "contributor"},
        "pull_request": pr(),
    }
    result = reconcile(api, 42, ENTRIES, event, apply=True)
    assert AUTO in result["remove"]


def test_stale_candidate_event_cannot_approve_new_head() -> None:
    api = FakeGitHub(pr(head={"sha": "new"}))
    event = {
        "action": "labeled",
        "label": {"name": AUTO},
        "sender": {"login": "maintainer"},
        "pull_request": pr(),
    }
    assert AUTO in reconcile(api, 42, ENTRIES, event, apply=True)["remove"]


def test_pagination_reads_every_page() -> None:
    class Pages(GitHub):
        def request(self, method: str, path: str, data: object = None) -> Any:
            assert method == "GET"
            if path.endswith("&page=1"):
                return [{"filename": f"file-{n}"} for n in range(100)]
            assert path.endswith("&page=2")
            return [{"filename": "last"}]

    assert len(Pages("owner/repo", "unused").pages("pulls/42/files")) == 101


def test_catalog_sync_preserves_unrelated_labels_and_is_dry_by_default() -> None:
    api = FakeGitHub()
    api.existing = [{"name": "unrelated", "description": "Keep me", "color": "ffffff"}]
    assert len(sync(api, ENTRIES, apply=False)) == len(ENTRIES)
    assert not api.writes
    sync(api, ENTRIES, apply=True)
    assert all(method == "POST" for method, _, _ in api.writes)
    api.existing = [{k: e[k] for k in ("name", "description", "color")} for e in ENTRIES]
    assert sync(api, ENTRIES, apply=True) == []


def test_cli_rejects_missing_credentials_without_network() -> None:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"GH_TOKEN", "GITHUB_TOKEN", "GITHUB_REPOSITORY"}
    }
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/pr-labels/pr_labels.py"),
            "sync",
            "--repo",
            "owner/repo",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert not result.stdout
    assert "GH_TOKEN or GITHUB_TOKEN are required" in result.stderr


def test_workflow_classification_does_not_execute_pr_source() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/pr-labels.yml").read_text())
    assert workflow["permissions"] == {"contents": "read", "pull-requests": "write"}
    checkout, reconcile_step = workflow["jobs"]["labels"]["steps"]
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    assert "${{" not in reconcile_step["run"]
    assert "pull_request.head" not in json.dumps(workflow)


@pytest.mark.parametrize(
    "name",
    [
        "pull-request-check",
        "git-policy",
        "cli-bench",
        "cli-playground",
        "boxie-lifecycle",
        "codeql",
    ],
)
def test_unrelated_labels_skip_expensive_jobs_and_cannot_cancel_ci(name: str) -> None:
    workflow = yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text())
    for job in workflow["jobs"].values():
        if not job.get("needs"):
            assert (
                "github.event.action != 'labeled' || github.event.label.name == 'run-ci'"
                in job["if"]
            )
    if "concurrency" in workflow:
        assert (
            "github.event.label.name != 'run-ci' && github.run_id"
            in workflow["concurrency"]["group"]
        )


def test_manual_recommendation_overrides_existing_candidate() -> None:
    desired, _ = desired_labels(
        pr(),
        [],
        ENTRIES,
        {"action": "labeled", "label": {"name": MANUAL}},
        authorized_candidate=True,
    )
    assert MANUAL in desired and AUTO not in desired


def test_dependabot_has_known_type_but_no_invented_risk() -> None:
    desired, errors = desired_labels(
        pr(body="Bumps a dependency", user={"login": "dependabot[bot]", "type": "Bot"}),
        [],
        ENTRIES,
        {},
        authorized_candidate=True,
    )
    assert "type:dependencies" in desired
    assert len(errors) == 2
    assert not any(label.startswith("risk:") for label in desired)
    assert AUTO not in desired


def test_reconcile_retries_changed_metadata_before_writing() -> None:
    class ChangingGitHub(FakeGitHub):
        reads = 0

        def request(self, method: str, path: str, data: object = None) -> Any:
            if method == "GET" and path == "pulls/42":
                self.reads += 1
                if self.reads == 2:
                    self.current["body"] = body("type:fix", "risk:high", "impact:persistence")
            return super().request(method, path, data)

    api = ChangingGitHub()
    result = reconcile(api, 42, ENTRIES, {}, apply=True)
    assert "risk:high" in result["add"]
    assert "risk:low" not in result["add"]
    assert AUTO in result["remove"]


@pytest.mark.parametrize(
    "name",
    [
        "pull-request-check",
        "git-policy",
        "cli-bench",
        "cli-playground",
        "boxie-lifecycle",
        "codeql",
    ],
)
def test_skipped_metadata_checks_cannot_replace_required_check_contexts(name: str) -> None:
    workflow = yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text())
    for job in workflow["jobs"].values():
        assert (
            "github.event.action == 'labeled' && github.event.label.name != 'run-ci'" in job["name"]
        )
        assert "' (label metadata only)' || ''" in job["name"]


def test_concurrent_label_removal_is_reconciled() -> None:
    class ConcurrentGitHub(FakeGitHub):
        raced = False

        def request(self, method: str, path: str, data: object = None) -> Any:
            result = super().request(method, path, data)
            if method == "POST" and path == "issues/42/labels" and not self.raced:
                self.raced = True
                self.current["labels"] = [
                    label for label in self.current["labels"] if label["name"] != MANUAL
                ]
            return result

    api = ConcurrentGitHub(pr(labels=[]))
    reconcile(api, 42, ENTRIES, {}, apply=True)
    assert MANUAL in {label["name"] for label in api.current["labels"]}
