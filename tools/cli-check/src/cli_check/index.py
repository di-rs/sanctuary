"""Generate the root README's Commands section from Cargo workspace members."""

import html
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from markdown_it import MarkdownIt
from markdown_it.token import Token

from cli_check.workspace import Package

REFRESH = "uv run --locked sdev index"
START = "<!-- BEGIN generated CLI index -->"
END = "<!-- END generated CLI index -->"


def purpose(package: Package) -> str:
    if package.description.strip():
        return package.description
    readme = package.directory / "README.md"
    if readme.is_file():
        tokens = MarkdownIt().parse(readme.read_text(encoding="utf-8"))
        for i, token in enumerate(tokens):
            if token.type == "heading_open" and token.tag != "h1":
                break
            if token.type == "paragraph_open" and token.level == 0:
                paragraph = "".join(
                    " " if child.type in {"softbreak", "hardbreak"} else child.content
                    for child in tokens[i + 1].children or []
                    if child.type in {"text", "code_inline", "softbreak", "hardbreak"}
                )
                if paragraph.strip():
                    return paragraph
    return ""


def command_table(root: Path, clis: list[Package], newline: str) -> str:
    rows = [START, "", "| Command | Purpose |", "| --- | --- |"]
    for package in clis:
        link = quote((package.directory / "README.md").relative_to(root).as_posix())
        label = package.name.replace("_", r"\_")
        plain = html.escape(" ".join(purpose(package).split()), quote=False)
        escaped = re.sub(r"([\\|`*_\[\]~])", r"\\\1", plain)
        rows.append(f"| [{label}]({link}) | {escaped} |")
    rows.extend(["", END, ""])
    return newline.join(rows)


def insert_table(source: str, tokens: list[Token], block: str, newline: str) -> str:
    """Bootstrap the marked region without replacing authored sections or examples."""
    lines = source.splitlines(keepends=True)
    headings = [
        (t.map, t.tag, tokens[i + 1].content)
        for i, t in enumerate(tokens)
        if t.type == "heading_open" and t.level == 0 and t.tag in {"h1", "h2"} and t.map
    ]
    commands = [span for span, tag, title in headings if tag == "h2" and title == "Commands"]
    if len(commands) > 1:
        raise ValueError(f"keep one '## Commands' section in the root README and run {REFRESH}")
    if commands:
        start = end = commands[0][1]
        stop = next((span[0] for span, _, _ in headings if span[0] >= start), len(lines))
        # Adopt an existing command table while preserving surrounding human-written Markdown.
        for token in tokens:
            span = token.map
            if token.type == "table_open" and token.level == 0 and span and start <= span[0] < stop:
                if re.fullmatch(
                    r"\s*\|\s*(?:Command|Project)\s*\|\s*Purpose\s*\|\s*", lines[span[0]]
                ):
                    start, end = span
                    break
        before, after = "".join(lines[:start]), "".join(lines[end:])
    else:
        before = (
            source
            + (newline if source.endswith(newline) else newline * 2)
            + "## Commands"
            + newline
        )
        after = ""
    if not before.endswith(newline * 2):
        before += newline
    if after and not after.startswith(newline):
        after = newline + after

    return before + block + after


def render(root: Path, packages: list[Package], source: str) -> str:
    clis = sorted((p for p in packages if p.is_cli), key=lambda p: p.name)
    lines = source.splitlines(keepends=True)
    tokens = MarkdownIt().enable("table").parse(source)
    markers = [
        (token.content.strip(), token.map)
        for token in tokens
        if token.type == "html_block"
        and token.level == 0
        and token.map
        and token.content.strip() in {START, END}
    ]
    newline = "\r\n" if "\r\n" in source else "\n"
    if not markers:
        # A standalone root binary already owns the root README.
        if not any(package.directory != root for package in clis):
            return source
        return insert_table(source, tokens, command_table(root, clis, newline), newline)
    if [marker for marker, _ in markers] != [START, END]:
        raise ValueError(
            f"restore one ordered pair of {START} and {END} in README.md, then run {REFRESH}"
        )
    start, end = markers[0][1][0], markers[1][1][1]
    return "".join(lines[:start]) + command_table(root, clis, newline) + "".join(lines[end:])


def refresh(root: Path, packages: list[Package], *, write: bool) -> bool:
    """Report drift and optionally replace the README atomically."""
    readme = root / "README.md"
    source = readme.read_text(encoding="utf-8", newline="")
    updated = render(root, packages, source)
    if updated == source:
        return False
    if write:
        with TemporaryDirectory(dir=root) as directory:
            stage = Path(directory) / "README.md"
            stage.write_text(updated, encoding="utf-8", newline="")
            shutil.copymode(readme, stage)
            stage.replace(readme)
    return True
