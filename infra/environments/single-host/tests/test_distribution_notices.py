"""Inspect notices in the artifacts built for distribution."""

import runpy
import subprocess
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.integration
@pytest.mark.parametrize(
    "package,source,notices",
    [
        (
            "boxie",
            "packages/boxie/src",
            ("boxie/sandbox/capture_bins/COPYRIGHT.musl", "boxie/sandbox/capture_bins/LICENSE.zig"),
        ),
        (
            "cli-playground",
            "tools/cli-playground/src",
            ("cli_playground/static/licenses.md", "cli_playground/static/tailwindcss.LICENSE"),
        ),
    ],
)
def test_release_wheel_notices(
    package: str, source: str, notices: tuple[str, str], tmp_path: Path
) -> None:
    subprocess.run(
        ["uv", "build", "--wheel", "--package", package, "--out-dir", str(tmp_path)],
        cwd=ROOT,
        check=True,
        timeout=60,
    )
    (wheel,) = tmp_path.glob("*.whl")
    with ZipFile(wheel) as archive:
        for filename in notices:
            assert archive.read(filename) == (ROOT / source / filename).read_bytes()


def test_wheel_notices_are_reproducible_and_missing_text_fails(tmp_path: Path) -> None:
    collect = runpy.run_path(str(ROOT / "infra/distribution/python_notices.py"))["collect_wheels"]
    site = tmp_path / "site-packages"
    for name, records in (
        ("modern", {"licenses/vendor/NOTICE": b"copyright and license\r\n"}),
        ("legacy", {"LICENSE": b"legacy text\n"}),
        ("project", {}),
    ):
        info = site / f"{name}-1.0.dist-info"
        info.mkdir(parents=True)
        metadata = f"Metadata-Version: 2.4\nName: {name}\nVersion: 1.0\n"
        if name == "modern":
            metadata += "License-File: vendor/NOTICE\n"
        (info / "METADATA").write_text(metadata)
        (info / "RECORD").write_text(
            "".join(f"{info.name}/{filename},,\n" for filename in ("METADATA", *records))
        )
        for filename, content in records.items():
            notice = info / filename
            notice.parent.mkdir(parents=True, exist_ok=True)
            notice.write_bytes(content)

    destination = tmp_path / "first"
    for bundle in (destination, tmp_path / "second"):
        assert collect(site, bundle, "project") == ["legacy 1.0", "modern 1.0", "project 1.0"]
        assert {path.name: path.read_bytes() for path in bundle.rglob("*") if path.is_file()} == {
            "LICENSE": b"legacy text\n",
            "NOTICE": b"copyright and license\r\n",
        }

    (site / "modern-1.0.dist-info/licenses/vendor/NOTICE").unlink()
    with pytest.raises(ValueError, match="Missing or empty notice file.*vendor/NOTICE"):
        collect(site, tmp_path / "missing-text", "project")

    (site / "modern-1.0.dist-info/RECORD").write_text("modern-1.0.dist-info/METADATA,,\n")
    with pytest.raises(ValueError, match="modern 1.0 is missing declared notice files"):
        collect(site, tmp_path / "missing-record", "project")


@pytest.mark.integration
@pytest.mark.parametrize(
    "component,dockerfile,context",
    [
        ("boxie", "packages/boxie/infra/Boxie.Dockerfile", "."),
        ("playground", "tools/cli-playground/infra/docker/CliPlayground.Dockerfile", "."),
        ("collector", "Dockerfile", "packages/boxie/infra/observability/collector"),
    ],
)
def test_release_container_notices(component: str, dockerfile: str, context: str) -> None:
    tag = f"sanctuary-notices-test:{uuid4().hex}"
    recipe = ROOT / context / dockerfile
    subprocess.run(
        ["docker", "build", "--platform", "linux/amd64", "-f", str(recipe), "-t", tag, context],
        cwd=ROOT,
        check=True,
        timeout=300,
    )
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--platform",
                "linux/amd64",
                "--network",
                "none",
                "--entrypoint",
                "/bin/sh",
                tag,
                "-ec",
                """
                dpkg-query -W -f '${db:Status-Status} ${Package}\n' > /tmp/notice-os-packages
                while read -r status package; do
                    if [ "$status" = installed ] && ! test -s "/usr/share/doc/$package/copyright"; then
                        echo "Missing OS copyright for $package" >&2
                        exit 1
                    fi
                done < /tmp/notice-os-packages
                test -s /usr/share/common-licenses/GPL-2
                cd /usr/share/sanctuary/notices
                case "$1" in
                    collector)
                        test -x /usr/local/bin/vector
                        test -s vector/copyright
                        test -s vector/NOTICE
                        test -s vector/LICENSE-3rdparty.csv
                        test -s vector/licenses/MPL-2.0
                        ;;
                    *)
                        test -s Sanctuary.LICENSE
                        test -s CPython.LICENSE
                        test -s os-packages.tsv
                        grep -q '^pip ' python-base-packages.txt
                        test -s python-base/pip-*/pip/_vendor/vendor.txt
                        test -s python-base/pip-*/pip/_vendor/packaging/LICENSE.APACHE
                        grep -q '"complete": false' native-wheel-review.json
                        grep -q 'psycopg-binary' native-wheel-review.json
                        test -s python/psycopg_binary-*/native/reviewed/PostgreSQL-18.6.COPYRIGHT
                        test -s python/psycopg_binary-*/native/reviewed/OpenSSL-3.5.9.LICENSE
                        test -s python/psycopg_binary-*/native/reviewed/Kerberos-1.22.2.NOTICE
                        test -s python/psycopg_binary-*/native/reviewed/OpenLDAP-2.6.16.LICENSE
                        test -s python/psycopg_binary-*/native/reviewed/libcom_err-1.42.9-19.el7.COPYING
                        test -s python/psycopg_binary-*/native/reviewed/cyrus-sasl-lib-2.1.26-24.el7_9.COPYING
                        test -s python/psycopg_binary-*/native/reviewed/keyutils-libs-1.5.8-3.el7.LICENCE.LGPL
                        test -s python/psycopg_binary-*/native/reviewed/Libxcrypt-4.5.2.LICENSING
                        test -s python/psycopg_binary-*/native/reviewed/Cython.LICENSE.txt
                        grep -q '^psycopg-binary ' python-packages.txt
                        ! grep -Eq '^(pytest|ruff|mypy) ' python-packages.txt || exit 1
                        if [ "$1" = boxie ]; then
                            test -s capture/LICENSE.zig
                            test -s capture/COPYRIGHT.musl
                            grep -q 'pkg:cargo/temporalio-client' native-wheel-review.json
                            test -s python/temporalio-*/native/reviewed/ring-0.17.14.LICENSE-BoringSSL
                            test -s python/temporalio-*/native/reviewed/zstd-sys-*.zstd-LICENSE
                            test -s python/protobuf-*/native/reviewed/Protobuf-33.6-utf8_range.LICENSE
                        else
                            set -- /app/.venv/lib/python*/site-packages/cli_playground/static
                            cmp frontend/licenses.md "$1/licenses.md"
                            cmp frontend/tailwindcss.LICENSE "$1/tailwindcss.LICENSE"
                        fi
                        ;;
                esac
                """,
                "check-release-notices",
                component,
            ],
            check=True,
            timeout=45,
        )
    finally:
        subprocess.run(["docker", "image", "rm", tag], check=True, timeout=30)


@pytest.mark.integration
def test_release_build_refuses_unverified_native_wheel_inputs() -> None:
    result = subprocess.run(
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "--progress=plain",
            "--build-arg",
            "NATIVE_NOTICE_POLICY=require-complete",
            "-f",
            "packages/boxie/infra/Boxie.Dockerfile",
            ".",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=300,
    )
    assert result.returncode != 0, "the release build accepted unverified native components"
    assert "Native wheel notices require verification" in result.stdout, result.stdout
    assert "pydantic_core" in result.stdout, result.stdout
