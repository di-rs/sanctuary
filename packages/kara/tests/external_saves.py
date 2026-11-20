"""Exercise save conflicts and recovery with disposable files and real PTYs."""

import os
import stat
import sys
import tempfile
from pathlib import Path

from pty_smoke import session

SAVE = b"\x13"
QUIT = b"\x11"
CONFLICT = b"File changed on disk. Use :w <filename> to save elsewhere."


def clean_save(binary: str, directory: Path) -> None:
    original = directory / "original"
    original.write_bytes(b"draft\n")

    def second_editor() -> None:
        session(binary, directory, [b"iExternal \x1b", SAVE, QUIT])
        assert original.read_bytes() == b"External draft\n"

    session(binary, directory, [second_editor, SAVE, QUIT])
    assert original.read_bytes() == b"External draft\n", "clean save overwrote the second editor"
    inode = original.stat().st_ino
    output = session(binary, directory, [SAVE, QUIT])
    assert original.stat().st_ino == inode, "clean save replaced an unchanged file"
    assert b"No changes to save" in output


def dirty_save(binary: str, directory: Path) -> None:
    original = directory / "original"
    original.write_bytes(b"draft\n")
    elsewhere = directory / "elsewhere"

    def change_in_place() -> None:
        times = original.stat()
        original.write_bytes(b"theirs")  # Same length and inode as the loaded file.
        os.utime(original, ns=(times.st_atime_ns, times.st_mtime_ns))

    def assert_preserved() -> None:
        assert original.read_bytes() == b"theirs", "dirty save overwrote external bytes"
        assert not elsewhere.exists()

    alternate_spelling = [b":w ORIGINAL\r"] if (directory / "ORIGINAL").is_file() else []

    output = session(
        binary,
        directory,
        [
            b"iMine \x1b",
            change_in_place,
            SAVE,
            assert_preserved,
            b":w ./original\r",
            assert_preserved,
            *alternate_spelling,
            assert_preserved,
            QUIT,
            b":w elsewhere\r",
            b"i!\x1b",
            SAVE,
            QUIT,
        ],
    )
    assert CONFLICT in output
    assert b"unsaved changes" in output
    assert original.read_bytes() == b"theirs"
    assert elsewhere.read_bytes() == b"Mine !draft\n", "Save As lost the unsaved buffer"
    assert stat.S_IMODE(elsewhere.stat().st_mode) == 0o600


def check_changed_entry(binary: str, directory: Path, *, replace: bool) -> None:
    original = directory / "original"
    original.write_bytes(b"draft\n")
    replacement = directory / "replacement"
    replacement.write_bytes(b"draft\n")
    replacement_inode = replacement.stat().st_ino

    def change_entry() -> None:
        if replace:
            replacement.replace(original)
        else:
            original.unlink()

    def assert_preserved() -> None:
        if replace:
            assert original.stat().st_ino == replacement_inode
            assert original.read_bytes() == b"draft\n"
        else:
            assert not original.exists(), "dirty save recreated a deleted file"

    output = session(
        binary,
        directory,
        [b"iMine \x1b", change_entry, SAVE, assert_preserved, b":w recovered\r", QUIT],
    )
    assert CONFLICT in output
    assert (directory / "recovered").read_bytes() == b"Mine draft\n"


def retargeted_link(binary: str, directory: Path) -> None:
    original = directory / "original"
    new_target = directory / "new-target"
    link = directory / "link"
    original.write_bytes(b"draft\n")
    new_target.write_bytes(b"external\n")
    link.symlink_to(original.name)

    def retarget() -> None:
        link.unlink()
        link.symlink_to(new_target.name)

    output = session(
        binary,
        directory,
        [b"iMine \x1b", retarget, SAVE, b":w ./link\r", b":q!\r"],
        args=(link.name,),
    )
    assert CONFLICT in output
    assert link.readlink() == Path(new_target.name)
    assert original.read_bytes() == b"draft\n"
    assert new_target.read_bytes() == b"external\n"


def new_file(binary: str, directory: Path) -> None:
    session(binary, directory, [b"iNew\x1b", SAVE, b"fresh\r", QUIT], args=())
    assert (directory / "fresh").read_bytes() == b"New"


def main() -> None:
    binary = str(Path(sys.argv[1]).resolve())
    for scenario in (clean_save, dirty_save, retargeted_link, new_file):
        with tempfile.TemporaryDirectory(prefix="kara-external-") as temp:
            scenario(binary, Path(temp))
    for replace in (True, False):
        with tempfile.TemporaryDirectory(prefix="kara-external-") as temp:
            check_changed_entry(binary, Path(temp), replace=replace)


if __name__ == "__main__":
    main()
