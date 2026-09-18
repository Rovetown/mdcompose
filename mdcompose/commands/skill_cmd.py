"""The skill command group: list, edit, remove, adopt.

Mirrors ``snippet_cmd.py`` command-for-command, over the skill library instead
of the snippet library. A thin adapter, same as its sibling: each command
parses arguments, resolves the skill library, calls into core, and formats
the result.
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
from mdcompose.core import files, skill_library_ops
from mdcompose.core import manifest as manifest_module
from mdcompose.core import platform as platform_module
from mdcompose.core import skills as skills_module
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.output import OutputContext
from mdcompose.prompts import confirm, output_for, prompt_choice

app = typer.Typer(
    name="skill",
    help="Manage the personal skill library.",
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
TagOption = Annotated[str | None, typer.Option("--tag", help="Only skills carrying this tag.")]
CategoryOption = Annotated[
    str | None, typer.Option("--category", help="Only skills in this category.")
]
ContentOption = Annotated[
    str | None,
    typer.Option(
        "--content", help="Replacement file contents. Supplying this skips the editor."
    ),
]
FileOption = Annotated[
    str | None,
    typer.Option(
        "--file",
        help="Which file to edit, relative to the skill's own directory. Defaults to SKILL.md.",
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
    typer.Argument(help="Skill ids to adopt. Defaults to every embedded skill."),
]


def resolve_library() -> skills_module.LibraryView:
    """Read the configured skill library once."""
    directory = platform_module.config_dir()
    configuration = config_module.load_config(config_module.config_path(directory))
    return skills_module.view(config_module.skill_library_dir(configuration, directory))


@app.command("list")
def list_skills(
    context: typer.Context,
    tag: TagOption = None,
    category: CategoryOption = None,
    quiet: QuietOption = False,
    json_output: JsonOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """List the skills in the skill library.

    Filters narrow rather than widen: supplying both a tag and a category
    lists only skills matching both. An empty skill library is reported, not
    an error.
    """
    output = output_for(context, quiet=quiet, json_output=json_output, no_colour=no_colour)
    library = resolve_library()
    matched = skills_module.filter_skills(library.skills, tag=tag, category=category)

    if output.json_mode:
        output.emit(_as_json(library, matched))
        return

    if library.is_empty:
        output.info(
            f"the skill library at {library.directory.as_posix()} is empty. "
            "Add one by writing a markdown file there, or 'mdcompose skill adopt'."
        )
        return
    if not matched:
        output.info("no skill matches that filter")
        return

    id_width = max(len(skill.id) for skill in matched)
    name_width = max(len(skill.display_name) for skill in matched)
    id_width = max(id_width, len("id"))
    name_width = max(name_width, len("name"))
    output.info(f"  {'id'.ljust(id_width)}  {'name'.ljust(name_width)}  description")
    for skill in matched:
        row_id = skill.id.ljust(id_width)
        row_name = skill.display_name.ljust(name_width)
        description = "" if skill.description is None else skill.description
        marker = " [bundle]" if skill.is_bundle else ""
        output.info(f"  {row_id}  {row_name}  {description}{marker}")


def _as_json(
    library: skills_module.LibraryView, matched: tuple[skills_module.Skill, ...]
) -> str:
    return json.dumps(
        {
            "library": library.directory.as_posix(),
            "skills": [
                {
                    "id": skill.id,
                    "title": skill.title,
                    "description": skill.description,
                    "tags": list(skill.tags),
                    "stack_signals": list(skill.stack_signals),
                    "category": skill.category,
                    "is_bundle": skill.is_bundle,
                }
                for skill in matched
            ],
        },
        indent=2,
        ensure_ascii=True,
    )


@app.command("edit")
def edit_skill(
    context: typer.Context,
    skill_id: Annotated[str, typer.Argument(help="The skill to edit.")],
    content: ContentOption = None,
    file: FileOption = None,
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Open a skill in the configured editor, or replace its contents directly.

    The result is validated before it is installed, so a broken edit leaves
    the existing skill exactly as it was. ``--file`` targets an accompanying
    file of a directory-shaped skill instead of ``SKILL.md``; naming one
    against a skill with no accompanying files is refused up front.
    """
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    library = resolve_library()
    skill = library.require(skill_id)
    if file is not None and file != skills_module.SKILL_MD_FILENAME and not skill.is_bundle:
        raise AttentionError(f"skill '{skill_id}' has no accompanying files")

    if content is not None:
        skill_library_ops.replace_body(library, skill_id, content, relative=file)
        output.info(f"wrote {skill_id}")
        return

    edited = _edit_in_editor(_edit_target_path(skill, file))
    if edited is None:
        output.info(f"{skill_id} unchanged")
        return
    skill_library_ops.replace_body(library, skill_id, edited, relative=file)
    output.info(f"wrote {skill_id}")


def _edit_target_path(skill: skills_module.Skill, file: str | None) -> Path:
    """Where to read the current content from for an interactive edit.

    A new accompanying file named by ``--file`` has no path yet; that is left
    to ``_edit_in_editor``, which treats a nonexistent path as empty content.
    """
    if file is None or file == skills_module.SKILL_MD_FILENAME:
        if skill.path is None:
            raise AttentionError(f"skill '{skill.id}' has no file on disk to edit")
        return skill.path
    assert skill.path is not None  # guaranteed by the is_bundle check in edit_skill
    return skill.path.parent / file


def _edit_in_editor(path: Path) -> str | None:
    """Open a copy in the editor and return the result, or None if unchanged.

    A copy rather than the file itself, so an edit that fails validation
    cannot leave the library holding it. A path that does not exist yet (a
    new accompanying file) starts from empty content rather than refusing.
    """
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        raise AttentionError(
            "no editor configured. Set VISUAL or EDITOR, or pass --content to "
            "supply the new contents directly."
        )
    original = files.read_text(path) if files.path_exists(path) else ""
    with tempfile.TemporaryDirectory() as scratch:
        draft = Path(scratch) / path.name
        files.write_text(draft, original)
        completed = subprocess.run([*shlex.split(editor), str(draft)], check=False)
        if completed.returncode != 0:
            raise AttentionError(f"editor exited with status {completed.returncode}")
        edited = files.read_text(draft)
    return None if files.content_equal(edited, original) else edited


@app.command("remove")
def remove_skill(
    context: typer.Context,
    skill_id: Annotated[str, typer.Argument(help="The skill to delete.")],
    yes: YesOption = False,
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Delete a skill from the skill library.

    Confirms first. Never touches a project that already composed it:
    composition copies content, so a composed file keeps working without its
    source skill.
    """
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    library = resolve_library()
    library.require(skill_id)

    if not confirm(output, f"delete skill '{skill_id}' from the skill library?", assume_yes=yes):
        output.info(f"kept {skill_id}")
        return
    skill_library_ops.remove_skill(library, skill_id)
    output.info(f"removed {skill_id}")


@app.command("adopt")
def adopt_skills(
    context: typer.Context,
    ids: IdsArgument = None,
    on_collision: OnCollisionOption = None,
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Save the skills embedded in this project's manifest into the skill library.

    Always explicit, never a side effect of composing, because pulling
    someone else's skills into a personal library should be a deliberate act.
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
    plan = skill_library_ops.plan_adopt(manifest, library, only=tuple(ids or ()))
    if plan.is_empty:
        output.info("the manifest embeds no skills")
        return

    resolutions = _resolve_collisions(output, plan, on_collision)
    result = skill_library_ops.apply_adopt(plan, library.directory, resolutions=resolutions)
    _report_adoption(output, result)


def _resolve_collisions(
    output: OutputContext,
    plan: skill_library_ops.AdoptPlan,
    on_collision: str | None,
) -> dict[str, skill_library_ops.Resolution]:
    """Decide what to do about each collision, by flag or by asking."""
    if not plan.collisions:
        return {}
    if on_collision is not None:
        decision = _validated_resolution(on_collision)
        return {collision.skill_id: decision for collision in plan.collisions}

    resolutions: dict[str, skill_library_ops.Resolution] = {}
    for collision in plan.collisions:
        output.warn(
            f"skill '{collision.skill_id}' already exists in the skill library with "
            "different content"
        )
        _show_difference(output, collision)
        answer = prompt_choice(
            output,
            f"skill '{collision.skill_id}'",
            options=skill_library_ops.RESOLUTIONS,
            default=skill_library_ops.KEEP,
            flag="--on-collision",
        )
        resolutions[collision.skill_id] = answer  # type: ignore[assignment]
    return resolutions


def _validated_resolution(candidate: str) -> skill_library_ops.Resolution:
    if candidate not in skill_library_ops.RESOLUTIONS:
        raise AttentionError(
            f"--on-collision must be one of {', '.join(skill_library_ops.RESOLUTIONS)}, "
            f"found '{candidate}'"
        )
    return candidate


def _show_difference(output: OutputContext, collision: skill_library_ops.Collision) -> None:
    """Show both versions of every differing file, so the choice is made with
    the content in view. A bundle skill's collision names each differing
    accompanying file; a plain skill's names none, since there is only ever
    the one file to show.
    """
    for path in collision.differing_paths:
        label = "" if path == skills_module.SKILL_MD_FILENAME else f" ({path})"
        output.info(f"  skill library copy of '{collision.skill_id}'{label}:")
        output.content_indented(collision.local.get(path, ""))
        output.info(f"  embedded copy of '{collision.skill_id}'{label}:")
        output.content_indented(collision.embedded.get(path, ""))


def _report_adoption(output: OutputContext, result: skill_library_ops.AdoptResult) -> None:
    for outcome, phrasing in (
        ("written", "adopted"),
        ("overwritten", "overwrote"),
        ("already-present", "already present"),
        ("kept", "kept the skill library copy of"),
    ):
        named = result.ids_with(outcome)  # type: ignore[arg-type]
        if named:
            output.info(f"  {phrasing}: {', '.join(named)}")
