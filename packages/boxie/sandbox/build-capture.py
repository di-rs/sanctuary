# /// script
# requires-python = ">=3.15"
# dependencies = ["ziglang==0.15.2"]
# ///
"""Rebuild the packaged Linux capture programs with Zig's pinned musl toolchain."""

import argparse
import gzip
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src" / "boxie" / "sandbox"
TARGETS = {"amd64": "x86_64-linux-musl", "arm64": "aarch64-linux-musl"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Run with uv run --no-project packages/boxie/sandbox/build-capture.py [--check].",
    )
    parser.add_argument(
        "--check", action="store_true", help="compare each packaged ELF with a fresh build"
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        executable = Path(directory) / "capture"
        for architecture, target in TARGETS.items():
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ziglang",
                    "cc",
                    "-target",
                    target,
                    "-std=c17",
                    "-Os",
                    "-static",
                    "-s",
                    "-Wl,--build-id=none",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "capture.c",
                    "-o",
                    str(executable),
                ],
                cwd=SOURCE,
                check=True,
            )
            resource = SOURCE / "capture_bins" / f"linux-{architecture}.gz"
            program = executable.read_bytes()
            if args.check:
                if not resource.is_file() or gzip.decompress(resource.read_bytes()) != program:
                    raise SystemExit(f"rebuild {resource.name} from capture.c")
            else:
                resource.parent.mkdir(exist_ok=True)
                resource.write_bytes(gzip.compress(program, compresslevel=9, mtime=0))


if __name__ == "__main__":
    main()
