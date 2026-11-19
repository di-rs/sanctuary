"""Resolved dependency identities, cycles and invalid lockfiles."""

import pytest
from cli_check.affected import lock_closures

LOCK = """
version = 4
[[package]]
name = "cli"
version = "0.1.0"
dependencies = ["helper"]
[[package]]
name = "helper"
version = "1.0.0"
source = "registry+https://example.invalid/index"
checksum = "original"
"""
OTHER_HELPER = """
[[package]]
name = "helper"
version = "{version}"
source = "git+https://example.invalid/repo#abc"
"""


@pytest.mark.parametrize("field", ["version", "source", "checksum"])
def test_dependency_identity_or_contents_change_the_consumers_closure(field: str) -> None:
    before = lock_closures(LOCK)
    changes = {
        "version": ('version = "1.0.0"', 'version = "2.0.0"'),
        "source": (
            "registry+https://example.invalid/index",
            "git+https://example.invalid/repo#abc",
        ),
        "checksum": ('checksum = "original"', 'checksum = "updated"'),
    }
    after = lock_closures(LOCK.replace(*changes[field]))
    assert before["cli"] != after["cli"]


@pytest.mark.parametrize(
    ("dependency", "other_version"),
    [
        ("helper 1.0.0", "2.0.0"),
        ("helper 1.0.0 (registry+https://example.invalid/index)", "1.0.0"),
    ],
)
def test_qualified_dependencies_resolve_the_same_package(
    dependency: str, other_version: str
) -> None:
    before = lock_closures(LOCK)
    after = lock_closures(
        LOCK.replace('["helper"]', f'["{dependency}"]') + OTHER_HELPER.format(version=other_version)
    )
    assert before["cli"] == after["cli"]


def test_dependency_cycles_terminate_and_retain_all_packages() -> None:
    cyclic = LOCK.replace('checksum = "original"', 'dependencies = ["cli"]')
    assert {key[0] for key in lock_closures(cyclic)["cli"]} == {"cli", "helper"}


@pytest.mark.parametrize(
    "content",
    [
        LOCK.replace('["helper"]', '["missing"]'),
        LOCK + '\n[[package]]\nname = "helper"\nversion = "2.0.0"\n',
        LOCK.replace('["helper"]', '["helper 1.0.0"]') + OTHER_HELPER.format(version="1.0.0"),
        LOCK + '\n[[package]]\nname = "cli"\nversion = "0.1.0"\n',
    ],
)
def test_unresolved_ambiguous_or_duplicate_dependencies_fail_instead_of_underselecting(
    content: str,
) -> None:
    with pytest.raises(ValueError):
        lock_closures(content)
