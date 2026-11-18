"""Check the content and first-use examples in package READMEs."""

from itertools import pairwise
from pathlib import Path

from markdown_it import MarkdownIt

from cli_check.diagnostics import Diagnostic
from cli_check.workspace import Package

EXAMPLE_MARKER = "<!-- cli-example -->"


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
        example = next(
            (
                (previous, token)
                for previous, token in pairwise(tokens[section:end])
                if token.type == "fence" and token.info.strip() in {"sh", "bash", "shell"}
            ),
            None,
        )
        if not (
            example
            and example[0].type == "html_block"
            and example[0].content == EXAMPLE_MARKER + "\n"
            and example[1].level == 0
            and example[1].info == "sh"
            and example[1].markup == "```"
        ):
            errors.append(
                Diagnostic(
                    path,
                    "docs",
                    "example",
                    f"put {EXAMPLE_MARKER} before the first runnable shell example"
                    " in the first section",
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
    for readme in dict.fromkeys(readmes):
        relative = readme.relative_to(root).as_posix()
        if not readme.is_file() or not readme.read_bytes().strip():
            errors.append(Diagnostic(relative, "docs", "readme", "requires a nonempty README.md"))
    for package in clis:
        readme = package.directory / "README.md"
        if readme.is_file():
            errors.extend(readme_style(root, readme, package.name))
    return errors
