"""Exercise the read-only audit workflow steps with disposable scanner reports."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
PYTHON_PINS = "Audit_Pkg==1.0\nother==2.0\nignored==1.0 ; python_version < '3'\n"
BOOT_LOCK = """\
importers:
  .:
    packageManagerDependencies:
      pnpm: {specifier: 12.9.1, version: 12.9.1}
packages:
  pnpm@12.9.1: {}
"""
PROJECT_LOCK = """\
importers:
  .:
    devDependencies:
      audit-pkg: {specifier: '1.0.0', version: '1.0.0'}
packages:
  audit-pkg@1.0.0: {}
"""


def python_report(case: str) -> dict[str, object]:
    dependency: dict[str, object] = {"name": "audit-pkg", "version": "1.0", "vulns": []}
    other: dict[str, object] = {"name": "other", "version": "2.0", "vulns": []}
    rows: list[dict[str, object]]
    match case:
        case "advisory":
            rows = [{**dependency, "vulns": [{"id": "fixture-advisory"}]}]
        case "empty":
            rows = []
        case "partial":
            rows = [dependency]
        case "wrong dependency":
            rows = [dependency, {**other, "name": "wrong"}]
        case "skipped":
            rows = [dependency, {"name": "other", "skip_reason": "fixture skip"}]
        case _:
            rows = [dependency, other]
    return {"dependencies": rows}


def frontend_report(case: str) -> dict[str, object]:
    counts = dict.fromkeys(("info", "low", "moderate", "high", "critical"), 0)
    advisories = {}
    if case == "advisory":
        advisories = {"1": {"title": "Fixture advisory", "severity": "info"}}
        counts["info"] = 1
    return {
        "advisories": advisories,
        "metadata": {
            "vulnerabilities": counts,
            "totalDependencies": {"empty": 0, "partial": 1, "project only": 1}.get(case, 2),
        },
    }


def write_command(path: Path, script: str) -> None:
    path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    path.chmod(0o755)


@pytest.mark.parametrize(
    "ecosystem,case,status,outcome",
    [
        (ecosystem, case, status, outcome)
        for ecosystem in ("python", "frontend")
        for case, status, outcome in (
            ("clean", 0, "Clean"),
            ("advisory", 1, "Affected"),
            ("empty", 0, "Incomplete"),
            ("partial", 0, "Incomplete"),
            ("unavailable", 124, "Incomplete"),
            ("invalid JSON", 0, "Incomplete"),
            ("unsuccessful clean report", 1, "Incomplete"),
        )
    ]
    + [
        ("python", "wrong dependency", 0, "Incomplete"),
        ("python", "skipped", 0, "Incomplete"),
        ("python", "export failed", 0, "Incomplete"),
        ("python", "empty export", 0, "Incomplete"),
        ("frontend", "boot only", 0, "Incomplete"),
        ("frontend", "project only", 0, "Incomplete"),
        ("frontend", "manager pin drift", 0, "Incomplete"),
        ("frontend", "boot specifier drift", 0, "Incomplete"),
        ("frontend", "boot resolution drift", 0, "Incomplete"),
        ("frontend", "missing boot package", 0, "Incomplete"),
        ("frontend", "missing lockfile", 0, "Incomplete"),
        ("frontend", "manifest drift", 0, "Incomplete"),
    ],
)
def test_audit_workflow(
    tmp_path: Path, ecosystem: str, case: str, status: int, outcome: str
) -> None:
    summary = tmp_path / "summary.md"
    definition = yaml.safe_load((ROOT / f".github/workflows/{ecosystem}-audit.yml").read_text())
    step = definition["jobs"]["audit"]["steps"][-1]["run"]
    (tmp_path / ".github").symlink_to(ROOT / ".github", target_is_directory=True)
    write_command(tmp_path / "uvx", 'shift 3\nexec "$AUDIT_TEST_PYTHON" "$@"')
    write_command(
        tmp_path / "uv",
        'if [ "$1" = export ]; then\n'
        '  printf "%s" "$AUDIT_REQUIREMENTS"\n'
        '  exit "$AUDIT_EXPORT_STATUS"\n'
        "fi\n"
        'shift 5\nexec "$AUDIT_TEST_PYTHON" "$@"',
    )
    write_command(tmp_path / "pnpm", 'printf "%s" "$AUDIT_REPORT"\nexit "$AUDIT_STATUS"')
    (tmp_path / "pip_audit.py").write_text(
        'import os\nprint(os.environ["AUDIT_REPORT"])\nraise SystemExit(int(os.environ["AUDIT_STATUS"]))\n'
    )
    frontend = tmp_path / "tools/cli-playground/frontend"
    frontend.mkdir(parents=True)
    frontend.joinpath("package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@12.9.2" if case == "manager pin drift" else "pnpm@12.9.1",
                "devDependencies": {"audit-pkg": "2.0.0" if case == "manifest drift" else "1.0.0"},
            }
        )
    )
    if case != "missing lockfile":
        lockfile = BOOT_LOCK if case == "boot only" else f"{BOOT_LOCK}---\n{PROJECT_LOCK}"
        if case == "project only":
            lockfile = PROJECT_LOCK
        elif case == "boot specifier drift":
            lockfile = lockfile.replace("specifier: 12.9.1", "specifier: 12.9.2")
        elif case == "boot resolution drift":
            lockfile = lockfile.replace("version: 12.9.1", "version: 12.9.2")
        elif case == "missing boot package":
            lockfile = lockfile.replace("pnpm@12.9.1: {}", "other@12.9.1: {}")
        frontend.joinpath("pnpm-lock.yaml").write_text(lockfile)
    report = python_report(case) if ecosystem == "python" else frontend_report(case)
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "PYTHONPATH": str(tmp_path),
            "AUDIT_TEST_PYTHON": sys.executable,
            "GITHUB_STEP_SUMMARY": str(summary),
            "AUDIT_REQUIREMENTS": "" if case == "empty export" else PYTHON_PINS,
            "AUDIT_EXPORT_STATUS": "1" if case == "export failed" else "0",
            "AUDIT_REPORT": "" if case in {"unavailable", "invalid JSON"} else json.dumps(report),
            "AUDIT_STATUS": str(status),
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == (0 if outcome == "Clean" else 1), result.stderr
    assert f"{ecosystem.title()} dependency audit — {outcome}." in summary.read_text()
    if case == "advisory":
        assert "fixture advisory" in result.stdout.lower() or "fixture-advisory" in result.stdout
        assert '"error"' not in result.stdout
