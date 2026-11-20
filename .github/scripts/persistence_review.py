"""Check the contributor's assessment for paths classified as production persistence."""

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml
from markdown_it import MarkdownIt

FIELDS = ("Production impact", "Existing-data validation", "Recovery")
POSTGRES = "infra/services/compose.postgres.yml"


def missing_evidence(body: str, upgrade: tuple[str, str] | None = None) -> list[str]:
    tokens = MarkdownIt().parse(re.sub(r"<!--.*?(?:-->|\Z)", "", body, flags=re.DOTALL))
    in_assessment = False
    ratings: set[str] = set()
    filled: dict[str, str] = {}
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and token.level == 0 and token.tag in {"h1", "h2"}:
            in_assessment = (
                token.tag == "h2" and tokens[i + 1].content.casefold() == "risk assessment"
            )
        if not in_assessment or token.type != "inline":
            continue
        text = token.content.strip()
        if match := re.match(r"^\[[xX]\]\s+`risk:(low|medium|high)`(?:\s|$)", text):
            ratings.add(match[1])
        for field in FIELDS:
            prefix = f"**{field}**"
            if text.startswith(prefix):
                value = text.removeprefix(prefix).strip(" :\t\n")
                if value.casefold().strip(".… ") not in {"", "tbd", "todo", "n/a", "none"}:
                    filled[field] = value
    missing = [field for field in FIELDS if field not in filled]
    if ratings != {"high"}:
        missing.insert(0, "select only `risk:high`")
    if upgrade and "Production impact" in filled:
        if any(not re.search(rf"(?<!\d){v}(?!\d)", filled["Production impact"]) for v in upgrade):
            missing.append(
                f"name the PostgreSQL {upgrade[0]} to {upgrade[1]} upgrade in Production impact"
            )
    return missing


def postgres_major(revision: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{revision}:{POSTGRES}"], capture_output=True, check=False
    )
    if result.returncode:
        return None
    image = yaml.safe_load(result.stdout)["services"]["db"]["image"]
    tag = re.search(r":(\d+)\b", image)
    return tag[1] if tag else None


def main(base: str, head: str, event: Path) -> None:
    labels = yaml.safe_load(Path(".github/labeler.yml").read_text())["labels"]
    rule = next(rule for rule in labels if rule["label"] == "risk:high")
    paths = rule["matcher"]["files"]["any"]
    changed = subprocess.check_output(
        ["git", "diff", "--no-renames", "--name-only", "-z", f"{base}...{head}", "--", *paths]
    )
    if not changed:
        return
    upgrade = None
    if POSTGRES.encode() in changed.split(b"\0"):
        ancestor = subprocess.check_output(["git", "merge-base", base, head], text=True).strip()
        old, new = postgres_major(ancestor), postgres_major(head)
        if old and new and old != new:
            upgrade = (old, new)
    missing = missing_evidence(json.loads(event.read_text())["pull_request"]["body"] or "", upgrade)
    if missing:
        raise SystemExit(
            "Complete the PR description under '## Risk Assessment'. Missing: "
            + ", ".join(missing)
            + ". Use '- **Production impact** ...', '- **Existing-data validation** ...', "
            "and '- **Recovery** ...'. Include the deployed data format and the evidence "
            "reviewers should verify before rollout."
        )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], Path(sys.argv[3]))
