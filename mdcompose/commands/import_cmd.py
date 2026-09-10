"""The import command: pull sections out of an existing CLAUDE.md or AGENTS.md.

`import` reads a file from anywhere on disk, never writing to it, lets the user
pick the sections worth keeping, and appends them to the current project's
AGENTS.md or CLAUDE.md, outside the managed block, in the region `init` never
touches.

The file is named ``import_cmd`` because ``import`` is a reserved word in Python.
The Typer command is still ``import``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from mdcompose.core import config as config_module
from mdcompose.core import files, import_ops, managed_block, sections
from mdcompose.core import platform as platform_module
from mdcompose.core import snippets as snippets_module
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.output import OutputContext
from mdcompose.prompts import is_interactive, output_for, prompt_choice

SourceArgument = Annotated[
    Path,
    typer.Argument(help="Path to the CLAUDE.md or AGENTS.md to import sections from."),
]
KeywordOption = Annotated[
    str | None,
    typer.Option(
        "--keyword",
        help="Only offer sections whose heading or content contains this text.",
    ),
]
SectionOption = Annotated[
    list[str] | None,
    typer.Option(
        "--section",
        help="Import the section with this heading. Repeatable. Bypasses the picker.",
    ),
]
ToClaudeOption = Annotated[
    bool,
    typer.Option("--to-claude", help="Apply the imported content to CLAUDE.md, not AGENTS.md."),
]
SaveAsSnippetOption = Annotated[
    str | None,
    typer.Option(
        "--save-as-snippet",
        help="Also save the extracted content to the snippet library under this name.",
    ),
]
CategoryOption = Annotated[
    str | None,
    typer.Option("--category", help="Category for the saved snippet's frontmatter."),
]
TagsOption = Annotated[
    str | None,
    typer.Option("--tags", help="Comma-separated tags for the saved snippet's frontmatter."),
]
OnCollisionOption = Annotated[
    str | None,
    typer.Option(
        "--on-collision",
        help="Resolve a snippet-name collision without asking: keep, overwrite, or rename.",
    ),
]
QuietOption = Annotated[bool, typer.Option("--quiet", "-q", help="Suppress informational output.")]
NoColourOption = Annotated[bool, typer.Option("--no-color", help="Never colourize output.")]


def register(app: typer.Typer) -> None:
    """Attach the command to an app under its real name."""
    app.command("import")(import_content)


def import_content(
    context: typer.Context,
    source: SourceArgument,
    keyword: KeywordOption = None,
    section_names: SectionOption = None,
    to_claude: ToClaudeOption = False,
    save_as_snippet: SaveAsSnippetOption = None,
    category: CategoryOption = None,
    tags: TagsOption = None,
    on_collision: OnCollisionOption = None,
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Import chosen sections of an existing file into this project's AGENTS.md.

    The source is read but never modified. Imported content is appended outside
    the target's managed block, so a later `init` neither overwrites nor removes
    it. With --save-as-snippet the same content is also written to the library.
    """
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    info = platform_module.detect_platform()
    source_path = _resolve_source(source, info, output)
    target = _target_path(to_claude)
    _reject_source_is_target(source_path, target)

    clean = managed_block.without_managed_blocks(files.read_text(source_path), source_path)
    parsed = sections.parse_sections(clean, source_name=source_path.name)
    if _nothing_importable(parsed):
        raise AttentionError(
            f"{source_path}: nothing to import, the file has no content outside an "
            "mdcompose managed block"
        )

    names = tuple(section_names or ())
    pool = _pool(output, parsed, keyword, names)
    if pool is None:
        return
    selected = import_ops.resolve_selection(
        pool, requested_headings=names or None, selector=_picker(output)
    )
    if not selected:
        output.info("nothing selected, nothing applied")
        return

    content = sections.extract(selected)
    if save_as_snippet is not None:
        _save_snippet(
            output, save_as_snippet, content, selected, source_path, category, tags, on_collision
        )

    import_ops.apply_to_target(target, content)
    plural = "" if len(selected) == 1 else "s"
    output.info(f"appended {len(selected)} section{plural} to {target.name}")


def _save_snippet(
    output: OutputContext,
    name: str,
    content: str,
    selected: tuple[sections.Section, ...],
    source_path: Path,
    category: str | None,
    tags: str | None,
    on_collision: str | None,
) -> None:
    """Persist the extracted content to the library, so it is reusable everywhere.

    A name that is already taken is resolved by the flag or by asking: an
    identical body is a silent no-op, a different one offers keep, overwrite, or
    a new name.
    """
    library = _resolve_library()
    heading = next((section.heading for section in selected if not section.synthetic), None)
    snippet = import_ops.build_snippet(
        name=name,
        body=content,
        source_path=source_path.as_posix(),
        source_heading=heading,
        category=category,
        tags=_split_tags(tags),
        today=datetime.now(UTC).date().isoformat(),
    )

    status = import_ops.snippet_status(library, snippet)
    if status == import_ops.IDENTICAL:
        output.info(f"snippet '{name}' is already in the library with this content")
        return
    if status == import_ops.NEW:
        import_ops.write_snippet(library, snippet)
        output.info(f"saved snippet '{name}'")
        return

    choice = _resolve_collision(output, library, snippet, on_collision)
    if choice == import_ops.KEEP:
        output.info(f"kept the library's existing '{name}'")
        return
    if choice == import_ops.OVERWRITE:
        import_ops.write_snippet(library, snippet, overwrite=True)
        output.info(f"overwrote snippet '{name}'")
        return
    renamed = import_ops.rename_snippet(snippet, _ask_new_name(output, library))
    import_ops.write_snippet(library, renamed)
    output.info(f"saved snippet '{renamed.id}'")


def _resolve_collision(
    output: OutputContext,
    library: snippets_module.LibraryView,
    snippet: snippets_module.Snippet,
    on_collision: str | None,
) -> import_ops.CollisionChoice:
    """Decide how to handle a name already taken by different content."""
    if on_collision is not None:
        return _validated_collision_choice(on_collision)
    if output.json_mode or not is_interactive():
        raise AttentionError(
            f"a snippet named '{snippet.id}' already exists with different content. "
            "Pass --on-collision with keep, overwrite, or rename."
        )
    existing = library.require(snippet.id)
    output.warn(f"snippet '{snippet.id}' already exists in the library with different content")
    output.info("  library copy:")
    output.content_indented(existing.body)
    output.info("  imported content:")
    output.content_indented(snippet.body)
    answer = prompt_choice(
        output,
        f"snippet '{snippet.id}'",
        options=import_ops.COLLISION_CHOICES,
        default=import_ops.KEEP,
        flag="--on-collision",
    )
    return answer  # type: ignore[return-value]


def _validated_collision_choice(candidate: str) -> import_ops.CollisionChoice:
    if candidate not in import_ops.COLLISION_CHOICES:
        raise AttentionError(
            f"--on-collision must be one of {', '.join(import_ops.COLLISION_CHOICES)}, "
            f"found '{candidate}'"
        )
    return candidate


def _ask_new_name(
    output: OutputContext, library: snippets_module.LibraryView
) -> str:
    """Ask for a snippet name not already in the library, refusing without a terminal."""
    if output.json_mode or not is_interactive():
        raise AttentionError(
            "choosing a new snippet name needs a terminal. Re-run with a different "
            "--save-as-snippet, or --on-collision with keep or overwrite."
        )
    while True:
        answer = typer.prompt("new snippet name", err=True).strip()
        try:
            candidate = snippets_module.validate_id(answer)
        except AttentionError as problem:
            output.warn(problem.message)
            continue
        if library.find(candidate) is not None:
            output.warn(f"'{candidate}' is also taken, choose another")
            continue
        return candidate


def _split_tags(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    return tuple(tag.strip() for tag in raw.split(",") if tag.strip())


def _resolve_library() -> snippets_module.LibraryView:
    directory = platform_module.config_dir()
    configuration = config_module.load_config(config_module.config_path(directory))
    return snippets_module.view(config_module.library_dir(configuration, directory))


def _resolve_source(raw: Path, info: platform_module.PlatformInfo, output: OutputContext) -> Path:
    """Resolve the source path, refusing what cannot be read as a file.

    A missing path and a directory are named and refused here. An existing file
    that cannot be read is refused by ``files.read_text`` with the same effect.
    """
    resolved = platform_module.resolve_path(raw, info)
    if not resolved.exists:
        raise AttentionError(f"{resolved.path}: no such file to import from")
    if resolved.path.is_dir():
        raise AttentionError(f"{resolved.path}: a file is required to import from, not a directory")
    if resolved.on_windows_mount:
        output.warn(
            f"{resolved.path.as_posix()} is on a Windows drive mounted under "
            f"{platform_module.WINDOWS_MOUNT_PREFIX}, which crosses the WSL and Windows "
            "filesystem boundary"
        )
    return resolved.path


def _target_path(to_claude: bool) -> Path:
    name = platform_module.CLAUDE_MD_NAME if to_claude else platform_module.AGENTS_MD_NAME
    return Path.cwd() / name


def _reject_source_is_target(source_path: Path, target_path: Path) -> None:
    if files.normalized_path(source_path) == files.normalized_path(target_path):
        raise AttentionError(f"{source_path}: a file cannot be imported into itself")


def _pool(
    output: OutputContext,
    parsed: tuple[sections.Section, ...],
    keyword: str | None,
    section_names: tuple[str, ...],
) -> tuple[sections.Section, ...] | None:
    """The sections a run may choose from, or None when there is nothing to do.

    A keyword narrows the pool. Naming sections directly overrides the keyword,
    which is then reported as unused rather than silently ignored.
    """
    if section_names:
        if keyword is not None:
            output.warn(f"--keyword '{keyword}' was not used because --section was given")
        return parsed
    if keyword is not None:
        matched = sections.filter_by_keyword(parsed, keyword)
        if not matched:
            output.info(f"no section matched '{keyword}'")
            return None
        return matched
    return parsed


def _picker(output: OutputContext) -> import_ops.SectionSelector | None:
    """Return an interactive section picker, or None when nobody can be asked."""
    if output.json_mode or not is_interactive():
        return None

    def pick(available: Sequence[sections.Section]) -> tuple[sections.Section, ...]:
        return _run_section_picker(available)

    return pick


def _run_section_picker(
    available: Sequence[sections.Section],
) -> tuple[sections.Section, ...]:
    """Ask which sections to import, showing each one's heading level.

    Imported here so the picker library loads only when a picker actually opens.
    """
    import questionary

    choices = [
        questionary.Choice(
            title=f"{'#' * section.level if section.level else '(file)'} {section.heading}",
            value=section,
        )
        for section in available
    ]
    answer = questionary.checkbox("Sections to import", choices=choices).ask()
    if answer is None:
        raise AttentionError("no selection made")
    return tuple(answer)


def _nothing_importable(parsed: tuple[sections.Section, ...]) -> bool:
    """Whether the source has no content outside a managed block worth offering."""
    if not parsed:
        return True
    return all(section.synthetic and not section.content.strip() for section in parsed)
