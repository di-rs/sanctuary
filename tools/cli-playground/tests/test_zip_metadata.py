"""Exercise fixed-size metadata reads with small disposable archives."""

import io
import struct
import zipfile
from unittest.mock import Mock

import pytest
from cli_playground import artifacts, zip_metadata

from .helpers import binary_bundle, elf_binary


def test_counts_actual_members_before_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = bytearray(binary_bundle(dict.fromkeys(("echor", "catr", "wcr"), elf_binary())))
    # The classic footer declares two entries while the tiny directory contains three.
    struct.pack_into("<HH", bundle, len(bundle) - 14, 2, 2)
    monkeypatch.setattr(artifacts, "MAX_CLIS", 1)
    parser = Mock(side_effect=AssertionError("eager ZIP parser called"))
    monkeypatch.setattr(zipfile, "ZipFile", parser)

    with pytest.raises(ValueError, match="too many archive members"):
        artifacts.binary_archive(bytes(bundle))

    parser.assert_not_called()


@pytest.mark.parametrize("prefix", [b"", b"bundle prefix"])
def test_valid_zip64_directory_remains_readable(
    prefix: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = io.BytesIO()
    with monkeypatch.context() as patch:
        patch.setattr(zipfile, "ZIP64_LIMIT", 1)
        with zipfile.ZipFile(output, "w") as bundle:
            bundle.writestr("echor", elf_binary())
            bundle.comment = b"preview build"

    data = prefix + output.getvalue()
    assert artifacts.binary_archive(data) == {"echor": elf_binary()}

    monkeypatch.setattr(zip_metadata, "MAX_DIRECTORY_BYTES", 46)
    parser = Mock(side_effect=AssertionError("eager ZIP parser called"))
    monkeypatch.setattr(zipfile, "ZipFile", parser)
    with pytest.raises(ValueError, match="ZIP central directory is too large"):
        artifacts.binary_archive(data)
    parser.assert_not_called()
