"""File type and syntax behavior observed through the executable."""

import os
import re
import sys
import tempfile
from pathlib import Path

from pty_smoke import session


def colored_text(output: bytes, color: int | tuple[int, int, int]) -> bytes:
    """Observe text in a foreground color, allowing combined SGR codes and cursor-only updates."""
    active = False
    cursor = 0
    rendered = bytearray()
    controls = rb"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07"
    for control in re.finditer(controls, output):
        if active:
            rendered.extend(output[cursor : control.start()])
        sequence = control.group()
        if sequence.startswith(b"\x1b[") and sequence.endswith(b"m"):
            codes = [int(code or b"0") for code in sequence[2:-1].split(b";")]
            index = 0
            while index < len(codes):
                code = codes[index]
                if code in (0, 39) or 30 <= code <= 37 or 90 <= code <= 97:
                    active = isinstance(color, int) and code == 30 + color
                elif code in (38, 48, 58) and index + 2 < len(codes):
                    if codes[index + 1] == 5:
                        if code == 38:
                            active = codes[index + 2] == color
                        index += 2
                    elif codes[index + 1] == 2 and index + 4 < len(codes):
                        if code == 38:
                            active = tuple(codes[index + 2 : index + 5]) == color
                        index += 4
                index += 1
        cursor = control.end()
    if active:
        rendered.extend(output[cursor:])
    return bytes(rendered)


def main() -> None:
    os.environ.pop("NO_COLOR", None)
    binary = str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory(prefix="kara-syntax-") as temp:
        directory = Path(temp)
        (directory / "original").write_bytes(b"let n = 12;\n")
        output = session(binary, directory, [b":w saved.RS\r", b"\x11"])
        assert b"| Text |" in output
        assert b"| Rust |" in output
        assert (directory / "saved.RS").read_bytes() == b"let n = 12;\n"
        output = session(binary, directory, [b":w missing/no.rs\r", b"\x11"])
        assert b"| Text |" in output
        assert b"| Rust |" not in output
        assert b"Could not save" in output
        for source, expected_red in [
            (b"f(1,2)", b"12"),
            ("界12".encode(), b""),
            (b"42u32 1.25f64 1e-3f32 1_000_isize 10bdh 1.25u32", b"42u321.25f641e-3f321_000_isize"),
            (
                b"0xFFu8 0b1010u32 0o77usize 0xCA_FE 0b2u8 0o8 0xGG 0xFFfoo",
                b"0xFFu80b1010u320o77usize0xCA_FE",
            ),
        ]:
            (directory / "original").write_bytes(source)
            output = session(binary, directory, [b":w numeric.rs\r", b"\x11"])
            assert colored_text(output, 1) == expected_red, repr(colored_text(output, 1))
            assert (directory / "numeric.rs").read_bytes() == source

        literals = (b"'a'", rb"'\''", rb"'\\'")
        source = b"; ".join(literals)
        (directory / "original").write_bytes(source)
        output = session(binary, directory, [b":w escaped_chars.rs\r", b"\x11"])
        assert colored_text(output, (255, 191, 0)) == b"".join(literals)
        assert (directory / "escaped_chars.rs").read_bytes() == source

        source = b"macro_rules! raw safe"
        (directory / "original").write_bytes(source)
        output = session(binary, directory, [b":w keywords.rs\r", b"\x11"])
        assert colored_text(output, 4) == b"macro_rulesrawsafe"
        assert (directory / "keywords.rs").read_bytes() == source


if __name__ == "__main__":
    main()
