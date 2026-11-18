"""Exercise the installed launcher without separately installed backend commands."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

LAUNCHER = Path(sys.executable).with_name("sdev")


@pytest.mark.parametrize(
    ("route", "runner", "delegate"),
    [
        ("check", "uv", ["cli-check", "verify"]),
        ("index", "uv", ["cli-check", "index"]),
        ("test", "cargo", []),
        ("bench", "uv", ["cli-bench"]),
        ("record", "uv", ["cli-record"]),
        ("local", "uv", ["local-dev"]),
        ("check-pr", "uv", ["cli-check", "check-pr"]),
    ],
)
def test_launch_from_worktree(tmp_path: Path, route: str, runner: str, delegate: list[str]) -> None:
    root = tmp_path / "a worktree"
    member = root / "tools/sanctuary-dev"
    member.mkdir(parents=True)
    (member / "pyproject.toml").touch()
    (root / "uv.lock").touch()
    (root / "Cargo.toml").touch()
    binary = tmp_path / runner
    binary.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "print(json.dumps([os.getcwd(), sys.argv[1:], sys.stdin.read()]))\n"
        "print('delegate diagnostic', file=sys.stderr)\n"
        "sys.exit(17)\n"
    )
    binary.chmod(0o755)
    forwarded = ["--", "--root", "a file with spaces", "", "--json"]
    env = {**os.environ, "PATH": str(tmp_path)}
    for cwd, prefix, expected_cwd in [
        (member, [], member),
        (tmp_path, ["--root", str(root)], root),
    ]:
        result = subprocess.run(
            [LAUNCHER, *prefix, route, *forwarded],
            cwd=cwd,
            env=env,
            input="delegate input",
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 17
        assert result.stderr == "delegate diagnostic\n"
        directory, args, stdin = json.loads(result.stdout)
        assert Path(directory) == expected_cwd.resolve() and stdin == "delegate input"
        assert "--locked" in args
        assert args[args.index("--") + 1 :] == [*delegate, *forwarded]
        if runner == "cargo":
            assert args[args.index("-p") + 1] == "cli-testing"
            assert Path(args[args.index("--manifest-path") + 1]) == root.resolve() / "Cargo.toml"
        else:
            assert args[args.index("--package") + 1] == delegate[0]
            assert Path(args[args.index("--project") + 1]) == root.resolve()


def test_checkout_required_only_for_delegation(tmp_path: Path) -> None:
    help_result = subprocess.run([LAUNCHER, "--help"], cwd=tmp_path, capture_output=True, text=True)
    assert help_result.returncode == 0 and "cli-testing" in help_result.stdout
    missing = subprocess.run(
        [LAUNCHER, "local", "status"], cwd=tmp_path, capture_output=True, text=True
    )
    assert missing.returncode == 1 and "sdev --root" in missing.stderr
