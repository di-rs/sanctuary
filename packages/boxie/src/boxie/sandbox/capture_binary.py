"""Stage the packaged Linux capture program on the supervisor's shared data volume."""

import gzip
import hashlib
import platform
import stat
from functools import cache
from importlib.resources import files
from pathlib import Path

from boxie.persistence.atomic import atomic_write

JOB_CAPTURE_PATH = "/.boxie-job-capture"
ARCHITECTURES = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


@cache
def _program(machine: str) -> tuple[str, bytes]:
    architecture = ARCHITECTURES.get(machine.lower())
    if architecture is None:
        raise RuntimeError(f"unsupported Linux job capture architecture: {machine}")
    resource = files(__package__).joinpath("capture_bins", f"linux-{architecture}.gz")
    program = gzip.decompress(resource.read_bytes())
    return hashlib.sha256(program).hexdigest(), program


def job_capture_mount(capture_root: Path) -> dict[str, object]:
    digest, program = _program(platform.machine())
    # The filename pins existing containers to their exact capture program across releases.
    target = capture_root / "job-capture" / digest
    try:
        attributes = target.lstat()
        valid = (
            stat.S_ISREG(attributes.st_mode)
            and stat.S_IMODE(attributes.st_mode) == 0o555
            and attributes.st_size == len(program)
            and target.read_bytes() == program
        )
    except FileNotFoundError:
        valid = False
    if not valid:
        atomic_write(target, program, mode=0o555)
    return {"Type": "bind", "Source": str(target), "Target": JOB_CAPTURE_PATH, "ReadOnly": True}
