"""The packaged capture program is a native Linux executable on each supported host."""

import hashlib
import platform
import stat
from pathlib import Path

import pytest
from boxie.sandbox import capture_binary


@pytest.mark.parametrize(
    ("machine", "elf_machine"), [("x86_64", 62), ("aarch64", 183), ("arm64", 183)]
)
def test_capture_mount_stages_verified_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, machine: str, elf_machine: int
) -> None:
    monkeypatch.setattr(platform, "machine", lambda: machine)
    mount = capture_binary.job_capture_mount(tmp_path)
    source = Path(str(mount["Source"]))
    data = source.read_bytes()
    assert mount == {
        "Type": "bind",
        "Source": str(source),
        "Target": "/.boxie-job-capture",
        "ReadOnly": True,
    }
    assert source.parent.parent == tmp_path
    assert data.startswith(b"\x7fELF") and int.from_bytes(data[18:20], "little") == elf_machine
    assert source.name == hashlib.sha256(data).hexdigest()
    assert stat.S_IMODE(source.stat().st_mode) == 0o555
    inode = source.stat().st_ino
    assert capture_binary.job_capture_mount(tmp_path) == mount
    assert source.stat().st_ino == inode
    source.chmod(0o755)
    source.write_bytes(b"damaged capture program")
    assert capture_binary.job_capture_mount(tmp_path) == mount
    assert source.read_bytes() == data and stat.S_IMODE(source.stat().st_mode) == 0o555
