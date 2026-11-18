import runpy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
ASSESSMENT = """## Risk Assessment

- [x] `risk:high`
- **Production impact** PostgreSQL 18 cannot open the deployed PostgreSQL 17 cluster.
- **Existing-data validation** The rehearsal preserved the cluster identifier and a sentinel row.
- **Recovery** Reattach the retained volume and restore the pinned PostgreSQL 17 image.
"""


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (ASSESSMENT, []),
        (
            "Updates `postgres` from 17.11 to 18.6",
            [
                "select only `risk:high`",
                "Production impact",
                "Existing-data validation",
                "Recovery",
            ],
        ),
        (ASSESSMENT.replace("risk:high", "risk:medium"), ["select only `risk:high`"]),
        (ASSESSMENT.replace("**Recovery**", "**Other**"), ["Recovery"]),
        (
            ASSESSMENT.replace(
                "Reattach the retained volume and restore the pinned PostgreSQL 17 image.",
                "<!-- describe it -->",
            ),
            ["Recovery"],
        ),
        (
            ASSESSMENT.replace(
                "- **Existing-data validation**", "\n## Testing\n\n- **Existing-data validation**"
            ),
            ["Existing-data validation", "Recovery"],
        ),
    ],
)
def test_contributor_evidence(body: str, expected: list[str]) -> None:
    check = runpy.run_path(str(ROOT / ".github/scripts/persistence_review.py"))["missing_evidence"]
    assert check(body) == expected


def test_major_change_requires_both_versions_in_the_impact() -> None:
    check = runpy.run_path(str(ROOT / ".github/scripts/persistence_review.py"))["missing_evidence"]
    assert check(ASSESSMENT, ("17", "18")) == []
    assert check(ASSESSMENT.replace("PostgreSQL 17", "the old"), ("17", "18"))


def test_database_updates_receive_persistence_labels_at_creation_and_review() -> None:
    updates = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())["updates"]
    directory = "/packages/boxie/infra/postgres"
    (postgres,) = [update for update in updates if update.get("directory") == directory]
    assert not any(directory in update.get("directories", []) for update in updates)
    assert "multi-ecosystem-group" not in postgres
    required = {"risk:high", "impact:persistence"}
    assert required <= set(postgres["labels"])
    rules = yaml.safe_load((ROOT / ".github/labeler.yml").read_text())["labels"]
    paths = {
        rule["label"]: rule["matcher"]["files"]["any"]
        for rule in rules
        if rule["label"] in required
    }
    assert paths["risk:high"] == paths["impact:persistence"]
    assert "packages/boxie/infra/postgres/**" in paths["risk:high"]
