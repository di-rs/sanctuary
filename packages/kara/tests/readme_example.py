"""Drive the README's edit, save, and quit steps in a real terminal."""

import sys
from pathlib import Path

from pty_smoke import session


def main() -> None:
    program, *args = sys.argv[1:]
    directory = Path.cwd()
    scratch = directory / "scratch.txt"
    scratch.write_bytes(b"world\n")
    output = session(program, directory, [b"ihello \x1b", b"\x13", b"\x11"], args=tuple(args))
    assert b"hello world" in output, output
    assert scratch.read_bytes() == b"hello world\n"


if __name__ == "__main__":
    main()
