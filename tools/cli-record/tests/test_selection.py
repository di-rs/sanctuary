"""An explicit selection is required before a recorder starts Docker."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from cli_record import command
from local_dev.stack import DevError


def test_record_requires_named_demos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/browser.toml").write_text(
        '[[cases]]\nname = "first"\nargs = []\n[[cases]]\nname = "second"\nargs = ["-n"]\n'
    )
    monkeypatch.setattr(command, "cli_package", lambda *_: SimpleNamespace(directory=tmp_path))
    for args in (["echor"], ["echor", "typo"]):
        with pytest.raises(DevError, match="first, second"):
            command.record(tmp_path, command.parser().parse_args(args))
