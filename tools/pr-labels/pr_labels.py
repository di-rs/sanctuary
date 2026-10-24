"""Synchronize the label catalog and reconcile PR metadata; dry-run by default.

Only trusted default-branch code runs in CI. PR text and filenames are data.
The catalog uses JSON syntax (a YAML subset) to avoid runtime dependencies.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AUTO = "auto-merge-candidate"
MANUAL = "manual-verification-required"
FAMILIES = ("type", "risk", "impact")
ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Classification:
    labels: frozenset[str]
    errors: tuple[str, ...]


def catalog(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if data.get("version") != 1:
        raise ValueError("Unsupported label catalog version")
    entries: list[dict[str, Any]] = data["labels"]
    names: set[str] = set()
    for entry in entries:
        name = entry["name"]
        if name in names or not isinstance(name, str) or len(name) > 50:
            raise ValueError("Invalid or duplicate label name")
        names.add(name)
        if not re.fullmatch(r"[0-9a-fA-F]{6}", entry["color"]):
            raise ValueError(f"Invalid color: {name}")
        if not 1 <= len(entry["description"]) <= 100:
            raise ValueError(f"Invalid description: {name}")
        if entry["owner"] not in {"author", "paths", "reviewer"}:
            raise ValueError(f"Invalid owner: {name}")
        if entry["owner"] == "paths" and not entry.get("paths"):
            raise ValueError(f"Missing paths: {name}")
    return entries


def classify(body: str, entries: list[dict[str, Any]]) -> Classification:
    """Parse only delimited checkbox groups; never infer from prose or titles."""
    selected: set[str] = set()
    errors: list[str] = []
    allowed = {e["name"] for e in entries if e["owner"] == "author"}
    for family in FAMILIES:
        start, end = f"<!-- labels:{family} -->", f"<!-- /labels:{family} -->"
        if body.count(start) != 1 or body.count(end) != 1:
            errors.append(f"Restore the {family} checkbox group from the PR template.")
            continue
        block = body.split(start, 1)[1].split(end, 1)[0]
        if body.index(end) < body.index(start):
            errors.append(f"Invalid {family} checkbox group boundaries.")
            continue
        choices = re.findall(r"^\s*- \[[xX]\] `([^`]+)`(?:\s.*)?$", block, re.MULTILINE)
        checked = re.findall(r"^\s*- \[[xX]\].*$", block, re.MULTILINE)
        valid = {name for name in allowed if name.startswith(family + ":")}
        if family == "impact":
            valid.add("impact:none")
        bad = (
            len(checked) != len(choices)
            or len(choices) != len(set(choices))
            or any(name not in valid for name in choices)
            or not choices
            or (family != "impact" and len(choices) != 1)
            or ("impact:none" in choices and len(choices) != 1)
        )
        if bad:
            errors.append(f"Select valid {family} options (one type/risk; impact:none alone).")
        else:
            selected.update(set(choices) - {"impact:none"})
    return Classification(frozenset(selected), tuple(errors))


def areas(files: list[dict[str, Any]], entries: list[dict[str, Any]]) -> set[str]:
    paths = {f[key] for f in files for key in ("filename", "previous_filename") if key in f}
    return {
        entry["name"]
        for entry in entries
        if entry["owner"] == "paths"
        and any(fnmatch.fnmatchcase(path, glob) for path in paths for glob in entry["paths"])
    }


def invalidate(event: dict[str, Any]) -> bool:
    action = event.get("action")
    if action in {"synchronize", "reopened", "converted_to_draft"}:
        return True
    if action == "labeled" and event.get("label", {}).get("name") == MANUAL:
        return True
    changes = event.get("changes", {})
    # Evidence edits invalidate verification even when checkboxes are unchanged.
    return "base" in changes or "body" in changes


def desired_labels(
    pr: dict[str, Any],
    files: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    event: dict[str, Any],
    *,
    authorized_candidate: bool,
) -> tuple[set[str], tuple[str, ...]]:
    current = {label["name"] for label in pr["labels"]}
    owned = {entry["name"] for entry in entries if entry["owner"] in {"author", "paths"}}
    selection = classify(pr.get("body") or "", entries)
    author = pr.get("user", {})
    if (
        author.get("login") == "dependabot[bot]"
        and author.get("type") == "Bot"
        and "<!-- labels:type -->" not in (pr.get("body") or "")
    ):
        selection = Classification(
            selection.labels | {"type:dependencies"},
            tuple(error for error in selection.errors if not error.startswith("Restore the type ")),
        )
    desired = (current - owned) | areas(files, entries) | set(selection.labels)
    candidate = (
        AUTO in current
        and not pr["draft"]
        and not selection.errors
        and "risk:low" in selection.labels
        and not invalidate(event)
        and authorized_candidate
    )
    desired.discard(AUTO if not candidate else MANUAL)
    desired.add(AUTO if candidate else MANUAL)
    return desired, selection.errors


class GitHub:
    def __init__(self, repo: str, token: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("Repository must be owner/name")
        self.repo = repo
        self.token = token

    def request(self, method: str, path: str, data: object = None) -> Any:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{self.repo}/{path}",
            data=None if data is None else json.dumps(data).encode(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            method=method,
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read()
            return json.loads(content) if content else None

    def pages(self, path: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, 101):
            batch = self.request("GET", f"{path}{separator}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise ValueError("Expected a paginated GitHub list")
            rows.extend(batch)
            if len(batch) < 100:
                return rows
        raise ValueError("Pagination limit reached; no partial classification will be applied")


def signature(pr: dict[str, Any]) -> tuple[object, ...]:
    return (
        pr["head"]["sha"],
        pr["base"]["sha"],
        pr["base"]["ref"],
        pr.get("body"),
        pr["draft"],
        pr["state"],
        tuple(sorted(label["name"] for label in pr["labels"])),
    )


def reconcile(
    api: GitHub,
    number: int,
    entries: list[dict[str, Any]],
    event: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    for _ in range(3):
        pr = api.request("GET", f"pulls/{number}")
        if pr["state"] != "open":
            return {"number": number, "skipped": "closed"}
        files = api.pages(f"pulls/{number}/files")
        if len(files) != pr["changed_files"]:
            raise ValueError(f"PR {number}: incomplete changed-file list; refusing partial labels")
        authorized = True
        if event.get("action") == "labeled" and event.get("label", {}).get("name") == AUTO:
            login = urllib.parse.quote(event["sender"]["login"], safe="")
            permission = api.request("GET", f"collaborators/{login}/permission")
            authorized = permission.get("permission") in {"admin", "maintain", "write"}
            # Do not grant candidacy against a newer revision than the label event.
            authorized = authorized and signature(pr)[:6] == signature(event["pull_request"])[:6]
        desired, errors = desired_labels(
            pr,
            files,
            entries,
            event,
            authorized_candidate=authorized,
        )
        current = {label["name"] for label in pr["labels"]}
        result = {
            "number": number,
            "head": pr["head"]["sha"],
            "add": sorted(desired - current),
            "remove": sorted(current - desired),
            "errors": list(errors),
            "applied": apply,
        }
        latest = api.request("GET", f"pulls/{number}")
        if signature(latest) != signature(pr):
            continue
        if apply:
            # Remove obsolete recommendations first; never PUT the entire label set.
            for label in result["remove"]:
                try:
                    api.request(
                        "DELETE", f"issues/{number}/labels/{urllib.parse.quote(label, safe='')}"
                    )
                except urllib.error.HTTPError as error:
                    if error.code != 404:
                        raise
            if result["add"]:
                api.request("POST", f"issues/{number}/labels", {"labels": result["add"]})
            # Concurrent events may have changed labels between the snapshot and writes.
            after = api.request("GET", f"pulls/{number}")
            managed = {entry["name"] for entry in entries if entry["name"] != "run-ci"}
            actual = {label["name"] for label in after["labels"]}
            if signature(after)[:6] != signature(pr)[:6] or actual & managed != desired & managed:
                continue
        return result
    raise ValueError(f"PR {number}: changed during reconciliation; retry against current metadata")


def sync(api: GitHub, entries: list[dict[str, Any]], *, apply: bool) -> list[dict[str, Any]]:
    existing = {label["name"]: label for label in api.pages("labels")}
    changes: list[dict[str, Any]] = []
    for entry in entries:
        fields = {key: entry[key] for key in ("name", "description", "color")}
        old = existing.get(entry["name"])
        if old and all(old[key] == value for key, value in fields.items()):
            continue
        changes.append(fields)
        if apply:
            if old:
                api.request(
                    "PATCH",
                    f"labels/{urllib.parse.quote(entry['name'], safe='')}",
                    {
                        "new_name": fields["name"],
                        "description": fields["description"],
                        "color": fields["color"],
                    },
                )
            else:
                api.request("POST", "labels", fields)
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("sync", "reconcile"))
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--catalog", type=Path, default=ROOT / ".github/labels.yml")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--event", type=Path)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not args.repo or not token:
        parser.error("--repo and GH_TOKEN or GITHUB_TOKEN are required")
    entries = catalog(args.catalog)
    api = GitHub(args.repo, token)
    if args.command == "sync":
        results: object = sync(api, entries, apply=args.apply)
    else:
        event = json.loads(args.event.read_text()) if args.event else {}
        number = args.pr or event.get("pull_request", {}).get("number")
        if not isinstance(number, int) or number <= 0:
            parser.error("reconcile requires --pr or a PR event")
        results = [reconcile(api, number, entries, event, apply=args.apply)]
    rendered = json.dumps(results, indent=2)
    print(rendered)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a") as file:
            file.write("## PR label reconciliation\n\n```json\n" + rendered + "\n```\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError) as failure:
        print(f"Label reconciliation failed: {failure}", file=sys.stderr)
        sys.exit(1)
