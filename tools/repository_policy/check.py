"""Compare Sanctuary's live default-branch merge policy with the checked-in ruleset."""

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from pydantic import AliasPath, BaseModel, Field, TypeAdapter, ValidationError

REPOSITORY = "di-rs/sanctuary"
RULESET = Path(__file__).resolve().parents[2] / ".github/rulesets/gitmoji-commits.json"
# The REST repository endpoint requires contents:write to return the merge settings.
REPOSITORY_QUERY = """query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { name }
    mergeCommitAllowed
    rebaseMergeAllowed
    squashMergeAllowed
  }
}"""

type MergeMethod = Literal["merge", "rebase", "squash"]


class RepositorySettings(BaseModel):
    default_branch: str = Field(
        validation_alias=AliasPath("defaultBranchRef", "name"), min_length=1
    )
    allow_merge_commit: bool = Field(validation_alias="mergeCommitAllowed")
    allow_rebase_merge: bool = Field(validation_alias="rebaseMergeAllowed")
    allow_squash_merge: bool = Field(validation_alias="squashMergeAllowed")

    def merge_methods(self) -> set[MergeMethod]:
        flags: dict[MergeMethod, bool] = {
            "merge": self.allow_merge_commit,
            "rebase": self.allow_rebase_merge,
            "squash": self.allow_squash_merge,
        }
        return {method for method, enabled in flags.items() if enabled}


class Rule(BaseModel):
    type: str
    parameters: object = None


class RefNames(BaseModel):
    include: list[str]
    exclude: list[str]


class Conditions(BaseModel):
    ref_name: RefNames


class CheckedInRuleset(BaseModel):
    target: Literal["branch"]
    enforcement: Literal["active"]
    conditions: Conditions
    rules: list[Rule]


class PullRequestParameters(BaseModel):
    allowed_merge_methods: Annotated[list[MergeMethod], Field(min_length=1)] = [
        "merge",
        "rebase",
        "squash",
    ]


class RequiredCheck(BaseModel, frozen=True):
    context: Annotated[str, Field(min_length=1)]
    integration_id: int | None = None

    def describe(self) -> str:
        source = f"app {self.integration_id}" if self.integration_id is not None else "any app"
        return f"{self.context!r} ({source})"


class StatusCheckParameters(BaseModel):
    required_status_checks: list[RequiredCheck]


@dataclass
class MergePolicy:
    required_checks: set[RequiredCheck]
    ruleset_methods: set[MergeMethod] | None


def collect_policy(rules: list[Rule]) -> MergePolicy:
    checks: set[RequiredCheck] = set()
    methods: set[MergeMethod] | None = None
    for rule in rules:
        if rule.type == "required_status_checks":
            params = StatusCheckParameters.model_validate(rule.parameters, strict=True)
            checks.update(params.required_status_checks)
        elif rule.type == "pull_request":
            allowed = PullRequestParameters.model_validate(rule.parameters, strict=True)
            if methods is None:
                methods = set(allowed.allowed_merge_methods)
            else:
                methods.intersection_update(allowed.allowed_merge_methods)
    return MergePolicy(checks, methods)


def github_api(endpoint: str, *args: str) -> bytes:
    command = ["gh", "api", "--hostname", "github.com", endpoint, *args]
    try:
        return subprocess.run(command, capture_output=True, check=True, timeout=30).stdout
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            f"GitHub API request to {endpoint} failed (gh exit {exc.returncode})"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"GitHub API request to {endpoint} timed out") from exc


def drift(expected: MergePolicy, live: MergePolicy, settings: RepositorySettings) -> list[str]:
    differences = []
    for check in sorted(
        item.describe() for item in expected.required_checks - live.required_checks
    ):
        differences.append(f"Missing required check {check}")
    for check in sorted(
        item.describe() for item in live.required_checks - expected.required_checks
    ):
        differences.append(f"Unexpected required check {check}")

    expected_methods = ", ".join(sorted(expected.ruleset_methods or ()))
    if live.ruleset_methods is None:
        differences.append("No active pull request rule applies to the default branch")
    elif live.ruleset_methods != expected.ruleset_methods:
        live_methods = ", ".join(sorted(live.ruleset_methods)) or "none"
        differences.append(
            f"Active ruleset merge methods are {live_methods} (expected {expected_methods})"
        )

    repo_methods = settings.merge_methods()
    if repo_methods != expected.ruleset_methods:
        enabled = ", ".join(sorted(repo_methods)) or "none"
        differences.append(f"Repository merge methods are {enabled} (expected {expected_methods})")
    return differences


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    source = RULESET.name
    try:
        local = CheckedInRuleset.model_validate_json(RULESET.read_bytes(), strict=True)
        if local.conditions.ref_name != RefNames(include=["~DEFAULT_BRANCH"], exclude=[]):
            raise ValueError("Checked-in ruleset must target the default branch")
        expected = collect_policy(local.rules)
        if not expected.ruleset_methods or not expected.required_checks:
            raise ValueError("Checked-in ruleset must specify merge methods and required checks")

        source = "GitHub repository settings"
        owner, name = REPOSITORY.split("/")
        response = github_api(
            "graphql",
            "--method",
            "POST",
            "--raw-field",
            f"query={REPOSITORY_QUERY}",
            "--raw-field",
            f"owner={owner}",
            "--raw-field",
            f"name={name}",
            "--jq",
            ".data.repository",
        )
        settings = RepositorySettings.model_validate_json(response, strict=True)
        branch = quote(settings.default_branch, safe="")
        source = "GitHub default-branch rules"
        response = github_api(
            f"repos/{REPOSITORY}/rules/branches/{branch}?per_page=100",
            "--method",
            "GET",
            "--paginate",
            "--slurp",
        )
        pages = TypeAdapter(list[list[Rule]]).validate_json(response, strict=True)
        live = collect_policy([rule for page in pages for rule in page])
    except ValidationError as exc:
        error = exc.errors(include_input=False, include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"]) or "JSON"
        print(
            f"Cannot compare merge policy. Invalid {location} in {source} ({error['type']}).",
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError) as exc:
        print(f"Cannot compare merge policy. {exc}", file=sys.stderr)
        return 2

    branch_label = f"{REPOSITORY} default branch {settings.default_branch!r}"
    differences = drift(expected, live, settings)
    if differences:
        print(f"Merge policy drift for {branch_label}")
        for difference in differences:
            print(f"- {difference}")
        return 1
    print(f"Merge policy matches for {branch_label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
