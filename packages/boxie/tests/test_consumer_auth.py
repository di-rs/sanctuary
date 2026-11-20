import hashlib
from pathlib import Path

from boxie.api.auth import ConsumerAuth
from boxie.domain.models import Principal


def test_revoking_one_grant_preserves_other_consumers(tmp_path: Path) -> None:
    auth = ConsumerAuth({"production": b"static"}, tmp_path)
    token_a, token_b = ("scoped." + c * 64 for c in "ab")
    grants = [tmp_path / hashlib.sha256(token.encode()).hexdigest() for token in (token_a, token_b)]
    grants[0].write_text("feature-a")
    grants[1].write_text("feature-b")
    assert auth.resolve("Bearer " + token_a) == Principal("feature-a", scoped=True)
    grants[0].unlink()
    assert not auth.accepts("Bearer " + token_a)
    assert auth.resolve("Bearer " + token_b).consumer_id == "feature-b"
    assert auth.resolve("Bearer static") == Principal("production")
    for invalid in ("production", "../other", ""):
        grants[0].write_text(invalid)
        assert not auth.accepts("Bearer " + token_a)
