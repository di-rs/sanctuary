"""Structured benchmark output remains parseable despite child tool chatter."""

import json
import subprocess
import sys

from conftest import RUNNER, Bench


def test_json_run_and_list(bench: Bench) -> None:
    bench.write_suite(
        'name = "sample"\nargs = []\nprepare = "printf prepare-output"\ncheck = "printf check-output"'
    )
    listed = subprocess.run(
        [sys.executable, str(RUNNER), str(bench.suite), "--json", "--list"],
        capture_output=True,
        text=True,
    )
    assert listed.returncode == 0
    assert json.loads(listed.stdout)["data"]["cases"][0]["name"] == "sample"
    assert not bench.output.exists()
    result = bench.run_bench("--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["data"]["completed_cases"] == ["sample"]
    assert "Benchmarking" in result.stderr


def test_json_doctor_and_argument_errors(bench: Bench) -> None:
    bench.write_suite()
    result = bench.run_bench("--json", "--doctor")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["data"]["auth"] == "not_required"
    assert not bench.output.exists()
    result = bench.run_bench("--json", "--unknown")
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["kind"] == "arguments"
    assert result.stderr == ""
    result = bench.run_bench("--json", "--doctor", "--hyperfine", "/missing/hyperfine")
    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False
    assert not bench.output.exists()


def test_suite_doctor_reports_run_executables(bench: Bench) -> None:
    release = bench.root / "target/release"
    release.mkdir(parents=True)
    (release / "fixture").symlink_to(bench.candidate)
    (release / "biggie").symlink_to(bench.biggie)
    bench.write_suite(
        top=f'reference = {json.dumps(str(bench.baseline))}\ngenerate = [["input.txt", "payload"]]'
    )
    command = [
        sys.executable,
        str(RUNNER),
        str(bench.suite),
        "--root",
        str(bench.root),
        "--hyperfine",
        str(bench.hyperfine),
        "--output",
        str(bench.output),
        "--runs",
        "1",
        "--json",
    ]
    tools = {
        "hyperfine": str(bench.hyperfine),
        "candidate": str(bench.candidate),
        "biggie": str(bench.biggie),
        "comparison": str(bench.baseline),
    }
    doctor = subprocess.run(
        [*command, "--doctor"], env=bench.env, capture_output=True, text=True, timeout=10
    )
    assert doctor.returncode == 0, doctor.stderr
    assert json.loads(doctor.stdout)["data"]["checks"] == [
        {"name": name, "ok": True, "path": path} for name, path in tools.items()
    ]
    assert not bench.events()
    assert not bench.output.exists()

    run = subprocess.run(command, env=bench.env, capture_output=True, text=True, timeout=10)
    assert run.returncode == 0, run.stderr
    metadata = json.loads((bench.output / "metadata.json").read_text())
    tools["baseline"] = tools.pop("comparison")
    assert metadata["executables"] == tools
