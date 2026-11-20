"""Provision the Compose-only consumer credential from the launcher's stdin."""

import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

directory = Path("/run/boxie")
with NamedTemporaryFile(dir=directory, delete=False) as file:
    temporary = Path(file.name)
    try:
        file.write(sys.stdin.buffer.read(4096))
        file.flush()
        os.replace(temporary, directory / "consumer")
    finally:
        temporary.unlink(missing_ok=True)
