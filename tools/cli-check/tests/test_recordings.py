"""PR evidence for direct CLI changes."""

import pytest
from cli_check.recordings import check_pr_recordings


def test_local_video_evidence_is_per_affected_cli() -> None:
    url = "https://github.com/user-attachments/assets/18d04903-90f8-4b10-83aa-99c9755a6735"
    body = f"#### `catr`\r\n\r\n{url}\r\n"
    check_pr_recordings(["catr"], body)
    check_pr_recordings([], "")
    check_pr_recordings(["echor"], "#### `echor`\n\nInternal change — Simplify an iterator.")
    with pytest.raises(ValueError, match="echor"):
        check_pr_recordings(["echor"], "#### `echor`\n\nInternal change — ")
    with pytest.raises(ValueError, match="echor"):
        check_pr_recordings(["catr", "echor"], body)
    with pytest.raises(ValueError, match="catr"):
        check_pr_recordings(["catr"], body.replace("github.com", "example.org"))
    with pytest.raises(ValueError, match="different"):
        check_pr_recordings(["catr", "echor"], body + f"#### `echor`\n\n{url}\n")
