"""Check nonempty package READMEs and their root index entries."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from cli_check.diagnostics import Diagnostic
from cli_check.workspace import Package


def local_links(path: Path) -> list[tuple[str, Path]]:
    links: list[tuple[str, Path]] = []
    for token in MarkdownIt().parse(path.read_text()):
        for child in token.children or []:
            value = (
                child.attrGet("href")
                if child.type == "link_open"
                else child.attrGet("src")
                if child.type == "image"
                else None
            )
            if not isinstance(value, str):
                continue
            url = urlsplit(value)
            if not url.scheme and not url.netloc and url.path:
                links.append((value, (path.parent / unquote(url.path)).resolve()))
    return links


def readme_style(root: Path, readme: Path, cli: str | None = None) -> list[Diagnostic]:
    path = readme.relative_to(root).as_posix()
    tokens = MarkdownIt().parse(readme.read_text())
    headings = [i for i, token in enumerate(tokens) if token.type == "heading_open"]
    errors = []
    if (
        not headings
        or headings[0] != 0
        or [tokens[i].tag for i in headings].count("h1") != 1
        or tokens[0].tag != "h1"
    ):
        errors.append(Diagnostic(path, "docs", "title", "start with one level-one title"))
    elif cli and tokens[1].content.casefold() != cli.casefold():
        errors.append(Diagnostic(path, "docs", "title", f"use the CLI name {cli} as the title"))
    section = headings[1] if len(headings) > 1 else len(tokens)
    if not any(
        token.type == "inline"
        and any(child.type == "text" and child.content.strip() for child in token.children or [])
        for token in tokens[3:section]
    ):
        errors.append(
            Diagnostic(path, "docs", "purpose", "introduce the component before its first section")
        )
    if cli:
        end = headings[2] if len(headings) > 2 else len(tokens)
        if not any(
            token.type == "fence"
            and token.info.strip() in {"sh", "bash", "shell"}
            and re.search(rf"(?<![\w-]){re.escape(cli)}(?![\w-])", token.content)
            for token in tokens[section:end]
        ):
            errors.append(
                Diagnostic(
                    path, "docs", "example", "show a runnable shell example in the first section"
                )
            )
    return errors


def component_docs(root: Path, packages: list[Package]) -> list[Diagnostic]:
    cli_readmes = {p.directory / "README.md" for p in packages if p.is_cli}
    readmes = {root / "README.md", *root.glob("infra/README.md")}
    for parent in ("packages", "tools", "utils"):
        readmes.update((root / parent).glob("*/README.md"))
    return [
        error
        for path in sorted(readmes - cli_readmes)
        if path.is_file()
        for error in readme_style(root, path)
    ]


def check(root: Path, packages: list[Package]) -> list[Diagnostic]:
    clis = [package for package in packages if package.is_cli]
    if not clis:
        return []
    errors: list[Diagnostic] = []
    readmes = [root / "README.md", *(package.directory / "README.md" for package in clis)]
    root_links: set[Path] = set()
    for readme in dict.fromkeys(readmes):
        relative = readme.relative_to(root).as_posix()
        if not readme.is_file() or not readme.read_bytes().strip():
            errors.append(Diagnostic(relative, "docs", "readme", "requires a nonempty README.md"))
            continue
        if readme == root / "README.md":
            root_links.update(target for _, target in local_links(readme))
    for package in clis:
        readme = package.directory / "README.md"
        if readme.is_file():
            errors.extend(readme_style(root, readme, package.name))
        if package.directory == root:
            continue
        if readme.resolve() not in root_links:
            errors.append(
                Diagnostic(
                    "README.md",
                    "docs",
                    "index",
                    f"root README must link {readme.relative_to(root).as_posix()}",
                )
            )
    return errors
