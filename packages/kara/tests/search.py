"""Search interactions through the executable with independent saved-byte checks."""

import sys
from pathlib import Path

from interaction import check


def main() -> None:
    binary = str(Path(sys.argv[1]).resolve())
    output = check(binary, b"abc", [b"/query\x7f", b"\x1b", b"i/?", b"\x1b", b"\x13\x11"], b"/?abc")
    assert b"/quer" in output
    check(binary, b"abc", [b"/query\r", b"iX", b"\x1b", b":w\r:q\r"], b"Xabc")

    output = check(binary, "é hit hit".encode(), [b"/hit\r", b"\x11"], "é hit hit".encode())
    assert b"2 matches; first at 1:3" in output

    source = "e\u0301x 👩‍💻".encode()
    for query, column in [("\u0301", 1), ("💻", 4)]:
        output = check(binary, source, [f"/{query}\r".encode(), b"\x11"], source)
        assert f"1 matches; first at 1:{column}".encode() in output


if __name__ == "__main__":
    main()
