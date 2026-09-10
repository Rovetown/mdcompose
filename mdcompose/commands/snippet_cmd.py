"""The snippet command group: list, edit, remove, adopt.

A thin adapter. Each command parses arguments, resolves the library, calls into
core, and formats the result. The prompting lives here and the outcome lives in
core, which is what lets a flag and an answered prompt reach the same code.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from mdcompose.core import config as config_module
from mdcompose.core import files, library_ops
from mdcompose.core import manifest as manifest_module
from mdcompose.core import platform as platform_module
from mdcompose.core import snippets as snippets_module
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.output import OutputContext
from mdcompose.prompts import confirm, output_for, prompt_choice

app = typer.Typer(
    name="snippet",
    help="Manage the personal snippet library.",
    rich_markup_mode=None,
    no_args_is_help=True,
)

QuietOption = Annotated[
    bool, typer.Option("--quiet", "-q", help="Suppress informational output.")
]
JsonOption = Annotated[
    bool, typer.Option("--json", help="Emit one JSON document on stdout and nothing else.")
]
NoColourOption = Annotated[bool, typer.Option("--no-color", help="Never colourize output.")]
TagOption = Annotated[str | None, typer.Option("--tag", help="Only snippets carrying this tag.")]
CategoryOption = Annotated[
    str | None, typer.Option("--category", help="Only snippets in this category.")
]
ContentOption = Annotated[
    str | None,
    typer.Option(
        "--content", help="Replacement file contents. Supplying this skips the editor."
    ),
]
YesOption = Annotated[bool, typer.Option("--yes", "-y", help="Answer yes to every confirmation.")]
OnCollisionOption = Annotated[
    str | None,
    typer.Option(
        "--on-collision",
        help="Resolve every collision without asking: keep or overwrite.",
    ),
]
IdsArgument = Annotated[
    list[str] | None,
    typer.Argument(help="Snippet ids to adopt. Defaults to every embedded snippet."),
]


def resolve_library() -> snippets_module.LibraryView:
    """Read the configured snippet library once."""
    directory = platform_module.config_dir()
    configuration = config_module.load_config(config_module.config_path(directory))
    return snippets_module.view(config_module.library_dir(configuration, directory))


@app.command("list")
def list_snippets(
    context: typer.Context,
    tag: TagOption = None,
    category: CategoryOption = None,
    quiet: QuietOption = False,
    json_output: JsonOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """List the snippets in the library.

    Filters narrow rather than widen: supplying both a tag and a category lists
    only snippets matching both. An empty library is reported, not an error.
    """
    output = output_for(context, quiet=quiet, json_output=json_output, no_colour=no_colour)
    library = resolve_library()
    matched = snippets_module.filter_snippets(library.snippets, tag=tag, category=category)

    if output.json_mode:
        output.emit(_as_json(library, matched))
        return

    if library.is_empty:
        output.info(
            f"the snippet library at {library.directory.as_posix()} is empty. "
            "Add one with 'mdcompose import <file> --save-as-snippet <name>'."
        )
        return
    if not matched:
        output.info("no snippet matches that filter")
        return

    id_width = max(len(snippet.id) for snippet in matched)
    name_width = max(len(snippet.display_name) for snippet in matched)
    id_width = max(id_width, len("id"))
    name_width = max(name_width, len("name"))
    output.info(f"  {'id'.ljust(id_width)}  {'name'.ljust(name_width)}  description")
    for snippet in matched:
        row_id = snippet.id.ljust(id_width)
        row_name = snippet.display_name.ljust(name_width)
        description = "" if snippet.description is None else snippet.description
        output.info(f"  {row_id}  {row_name}  {description}")


def _as_json(
    library: snippets_module.LibraryView, matched: tuple[snippets_module.Snippet, ...]
) -> str:
    return json.dumps(
        {
            "library": library.directory.as_posix(),
            "snippets": [
                {
                    "id": snippet.id,
                    "title": snippet.title,
                    "description": snippet.description,
                    "tags": list(snippet.tags),
                    "applies_to": snippet.applies_to,
                    "stack_signals": list(snippet.stack_signals),
                    "category": snippet.category,
                    "order": snippet.order,
                }
                for snippet in matched
            ],
        },
        indent=2,
        ensure_ascii=True,
    )


@app.command("edit")
def edit_snippet(
    context: typer.Context,
    snippet_id: Annotated[str, typer.Argument(help="The snippet to edit.")],
    content: ContentOption = None,
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Open a snippet in the configured editor, or replace its contents directly.

    The result is validated before it is installed, so a broken edit leaves the
    existing snippet exactly as it was.
    """
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    library = resolve_library()
    snippet = library.require(snippet_id)

    if content is not None:
        library_ops.replace_body(library, snippet_id, content)
        output.info(f"wrote {snippet_id}")
        return

    if snippet.path is None:
        raise AttentionError(f"snippet '{snippet_id}' has no file on disk to edit")
    edited = _edit_in_editor(snippet.path)
    if edited is None:
        output.info(f"{snippet_id} unchanged")
        return
    library_ops.replace_body(library, snippet_id, edited)
    output.info(f"wrote {snippet_id}")


def _edit_in_editor(path: Path) -> str | None:
    """Open a copy in the editor and return the result, or None if unchanged.

    A copy rather than the file itself, so an edit that fails validation cannot
    leave the library holding it.
    """
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        raise AttentionError(
            "no editor configured. Set VISUAL or EDITOR, or pass --content to "
            "supply the new contents directly."
        )
    original = files.read_text(path)
    with tempfile.TemporaryDirectory() as scratch:
        draft = Path(scratch) / path.name
        files.write_text(draft, original)
        completed = subprocess.run([*shlex.split(editor), str(draft)], check=False)
        if completed.returncode != 0:
            raise AttentionError(f"editor exited with status {completed.returncode}")
        edited = files.read_text(draft)
    return None if edited == original else edited


@app.command("remove")
def remove_snippet(
    context: typer.Context,
    snippet_id: Annotated[str, typer.Argument(help="The snippet to delete.")],
    yes: YesOption = False,
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Delete a snippet from the library.

    Confirms first. Never touches a project that already composed it: composition
    copies content, so a composed file keeps working without its source snippet.
    """
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    library = resolve_library()
    library.require(snippet_id)

    if not confirm(output, f"delete snippet '{snippet_id}' from the library?", assume_yes=yes):
        output.info(f"kept {snippet_id}")
        return
    library_ops.remove_snippet(library, snippet_id)
    output.info(f"removed {snippet_id}")


@app.command("adopt")
def adopt_snippets(
    context: typer.Context,
    ids: IdsArgument = None,
    on_collision: OnCollisionOption = None,
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Save the snippets embedded in this project's manifest into the library.

    Always explicit, never a side effect of composing, because pulling someone
    else's conventions into a personal library should be a deliberate act.
    Touches no project file and no manifest.
    """
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    project_root = Path.cwd()
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(project_root))
    if manifest is None:
        raise AttentionError(
            f"{project_root.as_posix()} has no {manifest_module.MANIFEST_FILENAME}, "
            "so there is nothing to adopt"
        )

    library = resolve_library()
    plan = library_ops.plan_adopt(manifest, library, only=tuple(ids or ()))
    if plan.is_empty:
        output.info("the manifest embeds no snippets")
        return

    resolutions = _resolve_collisions(output, plan, on_collision)
    result = library_ops.apply_adopt(plan, library.directory, resolutions=resolutions)
    _report_adoption(output, result)


def _resolve_collisions(
    output: OutputContext,
    plan: library_ops.AdoptPlan,
    on_collision: str | None,
) -> dict[str, library_ops.Resolution]:
    """Decide what to do about each collision, by flag or by asking."""
    if not plan.collisions:
        return {}
    if on_collision is not None:
        decision = _validated_resolution(on_collision)
        return {collision.snippet_id: decision for collision in plan.collisions}

    resolutions: dict[str, library_ops.Resolution] = {}
    for collision in plan.collisions:
        output.warn(
            f"snippet '{collision.snippet_id}' already exists in the library with "
            "different content"
        )
        _show_difference(output, collision)
        answer = prompt_choice(
            output,
            f"snippet '{collision.snippet_id}'",
            options=library_ops.RESOLUTIONS,
            default=library_ops.KEEP,
            flag="--on-collision",
        )
        resolutions[collision.snippet_id] = answer  # type: ignore[assignment]
    return resolutions


def _validated_resolution(candidate: str) -> library_ops.Resolution:
    if candidate not in library_ops.RESOLUTIONS:
        raise AttentionError(
            f"--on-collision must be one of {', '.join(library_ops.RESOLUTIONS)}, "
            f"found '{candidate}'"
        )
    return candidate


def _show_difference(output: OutputContext, collision: library_ops.Collision) -> None:
    """Show both versions, so the choice is made with the content in view."""
    output.info(f"  library copy of '{collision.snippet_id}':")
    output.content_indented(collision.local)
    output.info(f"  embedded copy of '{collision.snippet_id}':")
    output.content_indented(collision.embedded)


def _report_adoption(output: OutputContext, result: library_ops.AdoptResult) -> None:
    for outcome, phrasing in (
        ("written", "adopted"),
        ("overwritten", "overwrote"),
        ("already-present", "already present"),
        ("kept", "kept the library copy of"),
    ):
        named = result.ids_with(outcome)  # type: ignore[arg-type]
        if named:
            output.info(f"  {phrasing}: {', '.join(named)}")
