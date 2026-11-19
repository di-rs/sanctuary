"""Workflow contracts for privileged setup and ordinary Compose releases."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[3] / ".github/workflows"
QUEUE = {"group": "sanctuary-production", "queue": "max", "cancel-in-progress": "false"}


def workflow(filename: str) -> dict[str, Any]:
    result: dict[str, Any] = yaml.load((WORKFLOWS / filename).read_text(), Loader=yaml.BaseLoader)
    return result


def assert_source_uses_shared_selector(source: dict[str, Any]) -> None:
    assert source["uses"] == "./.github/workflows/select-production-source.yml"
    assert source["if"] == "${{ github.ref == 'refs/heads/master' }}"
    assert source["permissions"] == {"contents": "read"}
    assert "secrets" not in source


@pytest.mark.parametrize("attempt", ["1", "2"])
def test_production_source_exports_checked_out_revision_and_attempt(
    tmp_path: Path, attempt: str
) -> None:
    selector = workflow("select-production-source.yml")
    assert selector["on"] == {
        "workflow_call": {
            "outputs": {
                "sha": {"value": "${{ jobs.select.outputs.sha }}"},
                "attempt": {"value": "${{ jobs.select.outputs.attempt }}"},
            }
        }
    }
    assert "concurrency" not in selector
    selection = selector["jobs"]["select"]
    assert selection["permissions"] == {"contents": "read"}
    assert "environment" not in selection
    assert selection["outputs"] == {
        "sha": "${{ steps.revision.outputs.sha }}",
        "attempt": "${{ steps.revision.outputs.attempt }}",
    }
    checkout, record = selection["steps"]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"] == {"ref": "master", "persist-credentials": "false"}
    assert record["id"] == "revision"

    output = tmp_path / "github-output"
    root = WORKFLOWS.parents[1]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    subprocess.run(
        ["bash", "-euo", "pipefail", "-c", record["run"]],
        cwd=root,
        env={
            **os.environ,
            "GITHUB_SHA": "0" * 40,
            "GITHUB_RUN_ATTEMPT": attempt,
            "GITHUB_OUTPUT": str(output),
        },
        check=True,
    )
    assert output.read_text() == f"sha={head}\nattempt={attempt}\n"


@pytest.mark.parametrize(
    "filename,job_name,attempt_expression",
    [
        ("release-component.yml", "deploy", "${{ inputs.source_attempt }}"),
        ("sanctuary-setup.yml", "provision", "${{ needs.source.outputs.attempt }}"),
    ],
)
@pytest.mark.parametrize(
    "source_attempt,current_attempt,allowed",
    [("2", "2", True), ("1", "2", False), ("", "2", False)],
)
def test_deployment_rejects_partial_workflow_retry(
    filename: str,
    job_name: str,
    attempt_expression: str,
    source_attempt: str,
    current_attempt: str,
    allowed: bool,
) -> None:
    guarded = workflow(filename)["jobs"][job_name]["steps"][0]
    assert guarded["env"]["SOURCE_ATTEMPT"] == attempt_expression
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", guarded["run"]],
        env={**os.environ, "SOURCE_ATTEMPT": source_attempt, "GITHUB_RUN_ATTEMPT": current_attempt},
        text=True,
        capture_output=True,
    )
    assert (result.returncode == 0) == allowed
    if not allowed:
        assert "Re-run all jobs" in result.stderr


def test_setup_queues_before_selecting_master_and_builds_all_images() -> None:
    setup = workflow("sanctuary-setup.yml")
    assert setup["concurrency"] == QUEUE
    jobs = setup["jobs"]
    assert_source_uses_shared_selector(jobs["source"])
    for name, component in {
        "boxie": "boxie",
        "backend": "cli-playground",
        "sandbox": "boxie-sandbox",
        "collector": "collector",
    }.items():
        job = jobs[name]
        assert job["uses"] == "./.github/workflows/build-image.yml"
        assert job["needs"] == "source"
        assert job["with"] == {
            "component": component,
            "revision": "${{ needs.source.outputs.sha }}",
        }
    assert set(jobs["provision"]["needs"]) == {"source", "boxie", "backend", "sandbox", "collector"}
    assert "concurrency" not in jobs["provision"]


def test_reusable_builder_uses_fixed_components_without_deployment_secrets() -> None:
    builder = workflow("build-image.yml")
    job = builder["jobs"]["build"]
    assert set(builder["on"]) == {"workflow_call"}
    assert job["permissions"] == {"contents": "read", "packages": "write"}
    assert "Boxie.Dockerfile" in str(job)
    assert "CliPlayground.Dockerfile" in str(job)
    assert "packages/boxie/sandbox/Dockerfile" in str(job)
    assert "observability/collector" in str(job)
    assert "secrets." not in str(job)


@pytest.mark.parametrize(
    "filename,build_job,component,environment",
    [
        ("boxie-release.yml", "boxie", "boxie", "boxie"),
        ("boxie-release.yml", "sandbox", "boxie-sandbox", "boxie"),
        ("cli-playground-release.yml", "backend", "cli-playground", "cli-playground"),
    ],
)
def test_release_uses_one_queue_and_passes_the_selected_build(
    filename: str, build_job: str, component: str, environment: str
) -> None:
    release = workflow(filename)
    assert release["concurrency"] == QUEUE
    assert_source_uses_shared_selector(release["jobs"]["source"])
    deployment = release["jobs"][f"deploy-{build_job}"]
    assert deployment["uses"] == "./.github/workflows/release-component.yml"
    assert "concurrency" not in deployment
    assert deployment["permissions"] == {"contents": "read", "packages": "read"}
    assert deployment["with"] == {
        "component": component,
        "environment": environment,
        "source_sha": "${{ needs.source.outputs.sha }}",
        "source_attempt": "${{ needs.source.outputs.attempt }}",
        "built_sha": "${{ needs." + build_job + ".outputs.source_sha }}",
        "image": "${{ needs." + build_job + ".outputs.image }}",
    }
    assert deployment["secrets"] == {
        "DEPLOY_SSH_KEY": "${{ secrets.DEPLOY_SSH_KEY }}",
        "DEPLOY_KNOWN_HOSTS": "${{ secrets.DEPLOY_KNOWN_HOSTS }}",
    }


def test_shared_release_uses_protected_environment_and_direct_ssh() -> None:
    release = workflow("release-component.yml")
    assert set(release["on"]) == {"workflow_call"}
    assert release["on"]["workflow_call"]["secrets"] == {
        "DEPLOY_SSH_KEY": {"required": "true"},
        "DEPLOY_KNOWN_HOSTS": {"required": "true"},
    }
    assert "concurrency" not in release
    deployment = release["jobs"]["deploy"]
    assert "concurrency" not in deployment
    assert deployment["if"] == (
        "${{ github.ref == 'refs/heads/master' && vars.DEPLOYMENT_ACCEPTANCE_PASSED == 'true' }}"
    )
    assert deployment["environment"] == "${{ inputs.environment }}"
    assert deployment["permissions"] == {"contents": "read", "packages": "read"}
    _, checkout, deploy = deployment["steps"]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"] == {
        "ref": "${{ inputs.source_sha }}",
        "persist-credentials": "false",
    }
    assert deploy["run"] == 'bash infra/environments/single-host/release.sh "$COMPONENT"'
    assert deploy["env"] == {
        "COMPONENT": "${{ inputs.component }}",
        "SOURCE_SHA": "${{ inputs.source_sha }}",
        "BUILT_SHA": "${{ inputs.built_sha }}",
        "IMAGE": "${{ inputs.image }}",
        "DEPLOY_HOST": "${{ vars.DEPLOY_HOST }}",
        "DEPLOY_SSH_KEY": "${{ secrets.DEPLOY_SSH_KEY }}",
        "DEPLOY_KNOWN_HOSTS": "${{ secrets.DEPLOY_KNOWN_HOSTS }}",
        "GHCR_TOKEN": "${{ github.token }}",
    }


def test_releases_are_manual_and_keep_backend_separate_from_boxie() -> None:
    playground = workflow("cli-playground-release.yml")
    boxie = workflow("boxie-release.yml")
    assert playground["name"] == "🚀 cli-playground Release"
    assert boxie["name"] == "🚀 Boxie Release"
    for release, components in [
        (playground, {"backend": "cli-playground"}),
        (boxie, {"boxie": "boxie", "sandbox": "boxie-sandbox"}),
    ]:
        assert release["on"] == {"workflow_dispatch": {}}
        jobs = release["jobs"]
        assert set(jobs) == {"source", *components, *(f"deploy-{name}" for name in components)}
        for name, component in components.items():
            assert jobs[name]["needs"] == "source"
            assert jobs[name]["uses"] == "./.github/workflows/build-image.yml"
            assert jobs[name]["with"] == {
                "component": component,
                "revision": "${{ needs.source.outputs.sha }}",
            }
    assert set(boxie["jobs"]["deploy-boxie"]["needs"]) == {"source", "boxie", "sandbox"}
    assert set(boxie["jobs"]["deploy-sandbox"]["needs"]) == {"source", "sandbox", "deploy-boxie"}
    assert set(playground["jobs"]["deploy-backend"]["needs"]) == {"source", "backend"}
    assert not (WORKFLOWS / "boxie-sandbox-release.yml").exists()


def test_only_manual_setup_can_provision_cloud_resources() -> None:
    setup = workflow("sanctuary-setup.yml")
    assert set(setup["on"]) == {"workflow_dispatch"}
    provision = setup["jobs"]["provision"]
    assert provision["environment"] == "sanctuary"
    assert {"HCLOUD_TOKEN", "CLOUDFLARE_API_TOKEN"} <= set(provision["env"])
    assert any(
        step.get("working-directory") == "infra/environments/single-host"
        for step in provision["steps"]
    )
    commands = "\n".join(step.get("run", "") for step in provision["steps"])
    assert commands.index("pulumi up") < commands.index("render_inputs")
    assert "cloud-init status --wait" in commands
    assert "install.sh" in commands
    assert "submit-release.sh" not in commands


def test_deployment_ssh_keeps_silent_readiness_checks_connected(tmp_path: Path) -> None:
    library = WORKFLOWS.parent.parent / "infra/environments/single-host/deployment.shlib"
    subprocess.run(
        [
            "bash",
            "-eu",
            "-c",
            'umask 077\nsource "$1"\nwrite_deployment_ssh_config "$2" example.com',
            "deployment-ssh-config",
            str(library),
            str(tmp_path),
        ],
        check=True,
    )
    config = tmp_path / "config"
    result = subprocess.run(
        ["ssh", "-G", "-F", str(config), "deployment"],
        capture_output=True,
        text=True,
        check=True,
    )
    settings = dict(line.split(" ", 1) for line in result.stdout.splitlines())
    assert 0 < int(settings["serveraliveinterval"]) <= 60
    assert int(settings["serveralivecountmax"]) >= 3
    assert settings["stricthostkeychecking"] == "true"
    assert settings["hostname"] == "example.com"
    assert settings["identityfile"] == str(tmp_path / "key")
    assert settings["userknownhostsfile"] == str(tmp_path / "known_hosts")
    assert config.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("status", [0, 1, 2])
def test_setup_reports_bootstrap_failure_without_ignoring_it(status: int) -> None:
    commands = "\n".join(
        step.get("run", "")
        for step in workflow("sanctuary-setup.yml")["jobs"]["provision"]["steps"]
    )
    remote = commands.split("<<'BOOTSTRAP'\n", 1)[1].split("\nBOOTSTRAP", 1)[0]
    result = subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            (
                f"cloud-init() {{ echo bootstrap-status; return {status}; }}\n"
                "tail() { echo bootstrap-diagnostics; return 1; }\n"
                "journalctl() { return 1; }\n" + remote
            ),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == status
    assert "bootstrap-status" in result.stdout
    assert ("bootstrap-diagnostics" in result.stdout) == (status != 0)


@pytest.mark.parametrize("status", [0, 1, 2])
def test_setup_stops_before_upload_when_bootstrap_fails(status: int) -> None:
    script = workflow("sanctuary-setup.yml")["jobs"]["provision"]["steps"][-1]["run"]
    script = script[script.index("echo 'Waiting for host bootstrap'") :]
    result = subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            "private=/unused\nremote=/unused\n"
            f"ssh() {{ cat >/dev/null; return {status}; }}\n"
            "scp() { echo uploaded; }\n" + script,
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == status
    assert ("uploaded" in result.stdout) == (status == 0)


def test_setup_pulls_all_images_before_starting_boxie() -> None:
    installer = (WORKFLOWS.parent.parent / "infra/environments/single-host/install.sh").read_text()
    assert "BOXIE_SANDBOX_IMAGE" in installer
    assert installer.index('docker pull "$image"') < installer.index(
        "bash /opt/sanctuary/boxie/install.sh"
    )


def test_preview_controller_keeps_privileged_code_on_the_default_branch() -> None:
    preview = workflow("cli-playground-preview.yml")
    assert preview["on"]["workflow_run"] == {
        "workflows": ["🏗️ cli-playground PR binary builds"],
        "types": ["in_progress", "completed"],
    }
    assert preview["on"]["pull_request_target"] == {
        "branches": ["master"],
        "types": ["closed", "reopened"],
    }
    assert preview["permissions"] == {}
    assert set(preview["jobs"]) == {"publish", "lifecycle"}
    for job in preview["jobs"].values():
        assert job["environment"] == {"name": "cli-playground-preview", "deployment": "false"}
        checkout = job["steps"][0]
        assert checkout["with"] == {
            "ref": "${{ github.event.repository.default_branch }}",
            "persist-credentials": "false",
        }
        assert job["permissions"]["contents"] == "read"
        assert "CLOUDFLARE_DNS_API_TOKEN" not in str(job)
    assert "github.event_name == 'workflow_run'" in preview["jobs"]["publish"]["if"]
    assert "conclusion" not in preview["jobs"]["publish"]["if"]
    assert "github.event_name == 'pull_request_target'" in preview["jobs"]["lifecycle"]["if"]


def test_infrastructure_checks_require_trusted_dispatch_or_opted_in_schedule() -> None:
    path = WORKFLOWS / "sanctuary-infra-check.yml"
    assert path.exists(), "Protected infrastructure review workflow is missing"
    check = workflow("sanctuary-infra-check.yml")
    assert set(check["on"]) == {"workflow_dispatch", "schedule"}
    selection = check["jobs"]["revision"]
    assert "github.ref == 'refs/heads/master'" in selection["if"]
    assert "vars.SANCTUARY_INFRA_DRIFT_CHECK == 'true'" in selection["if"]
    assert "environment" not in selection
    assert "secrets." not in str(selection)
    protected = check["jobs"]["check"]
    assert protected["needs"] == "revision"
    assert protected["environment"] == "sanctuary"
    assert protected["permissions"] == {"contents": "read"}
    assert check["concurrency"] == {
        "group": "sanctuary-production",
        "queue": "max",
        "cancel-in-progress": "false",
    }
    preview = next(step for step in protected["steps"] if step.get("id") == "preview")
    assert "concurrency" not in protected
    assert preview["with"]["command"] == "preview"
    assert preview["with"]["upsert"] == "false"
    assert preview["with"]["suppress-outputs"] == "true"
    assert preview["with"]["comment-on-summary"] == "true"
    assert preview["with"]["comment-on-pr"] == "false"


def test_infrastructure_review_does_not_stage_application_installation() -> None:
    steps = workflow("sanctuary-infra-check.yml")["jobs"]["check"]["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)
    assert ".installation" not in commands
    assert "sourceDirectory" not in commands


@pytest.mark.parametrize("requested", ["default", "head", "HEAD", "master", "0" * 40, "x\nrun=bad"])
def test_infrastructure_review_resolves_only_existing_full_commit_ids(
    tmp_path: Path, requested: str
) -> None:
    path = WORKFLOWS / "sanctuary-infra-check.yml"
    assert path.exists(), "Protected infrastructure review workflow is missing"
    selection = workflow("sanctuary-infra-check.yml")["jobs"]["revision"]
    script = next(step["run"] for step in selection["steps"] if step.get("id") == "resolve")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    revision = "" if requested == "default" else head if requested == "head" else requested
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        env={
            **os.environ,
            "REQUESTED_REVISION": revision,
            "GITHUB_SHA": head,
            "GITHUB_OUTPUT": str(output),
        },
        text=True,
        capture_output=True,
    )
    if requested in {"default", "head"}:
        assert result.returncode == 0, result.stderr
        assert output.read_text() == f"revision={head}\n"
    else:
        assert result.returncode != 0
        assert not output.exists()


@pytest.mark.parametrize("exit_code", [0, 2, 255])
def test_drift_check_only_previews_refresh_and_preserves_failure_status(
    tmp_path: Path, exit_code: int
) -> None:
    steps = workflow("sanctuary-infra-check.yml")["jobs"]["check"]["steps"]
    script = next(step["run"] for step in steps if "Detect drift" in step.get("name", ""))
    calls = tmp_path / "calls"
    binary = tmp_path / "pulumi"
    binary.write_text(
        f"#!{sys.executable}\nimport pathlib, sys\n"
        f"with pathlib.Path({str(calls)!r}).open('a') as target:\n"
        "    target.write(' '.join(sys.argv[1:]) + '\\n')\n"
        f"sys.exit({exit_code} if sys.argv[1] == 'refresh' else 0)\n"
    )
    binary.chmod(0o755)
    summary = tmp_path / "summary"
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "PULUMI_BACKEND_URL": "file:///review-state",
            "GITHUB_STEP_SUMMARY": str(summary),
        },
        text=True,
        capture_output=True,
    )
    assert result.returncode == exit_code, result.stderr
    assert calls.read_text().splitlines() == [
        "login file:///review-state --non-interactive",
        "stack select production --non-interactive",
        "refresh --preview-only --expect-no-changes --non-interactive --diff --suppress-outputs",
    ]
    assert (
        "No drift detected." if exit_code == 0 else "Drift check failed."
    ) in summary.read_text()


def test_legacy_ssh_transport_has_no_remaining_entrypoints() -> None:
    root = WORKFLOWS.parent.parent
    for path in (
        "tools/cli-playground/infra/playground_infra/deploy.py",
        "tools/cli-playground/infra/playground_infra/ci.py",
        "infra/environments/single-host/configure-github.sh",
    ):
        assert not (root / path).exists()
