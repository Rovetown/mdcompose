"""The eject command: stop mdcompose managing a directory.

Removes the managed block markers from a target's files and deletes its
``mdcompose.lock``. The block content stays as plain markdown by default so the
files keep working; ``--strip`` removes it too. Everything outside a block,
including anything `import` or `convert` added, is left exactly as it was, and
the snippet library is never touched.

Re-running `init` after an eject adds a fresh managed block alongside whatever
was kept. Ejecting is not a reversible toggle.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer

from mdcompose.core import config as config_module
from mdcompose.core import eject as eject_module
from mdcompose.core import files, managed_block
from mdcompose.core import platform as platform_module
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.output import OutputContext
from mdcompose.prompts import is_interactive, output_for

DirectoryArgument = Annotated[
    Path | None,
    typer.Argument(help="Directory to eject. Defaults to the current directory."),
]
StripOption = Annotated[
    bool,
    typer.Option("--strip", help="Remove the block content too, not just the markers."),
]
GlobalOption = Annotated[
    bool, typer.Option("--global", help="Eject the global file pair instead of a project.")
]
YesOption = Annotated[
    bool, typer.Option("--yes", "-y", help="Confirm the eject without a prompt.")
]
QuietOption = Annotated[bool, typer.Option("--quiet", "-q", help="Suppress informational output.")]
NoColourOption = Annotated[bool, typer.Option("--no-color", help="Never colourize output.")]


def register(app: typer.Typer) -> None:
    """Attach the command to an app under its real name."""
    app.command("eject")(eject)


def eject(
    context: typer.Context,
    directory: DirectoryArgument = None,
    strip: StripOption = False,
    global_scope: GlobalOption = False,
    yes: YesOption = False,
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Take mdcompose's markers back out of a directory and delete its manifest.

    The block content is kept as plain markdown unless --strip is given. Content
    outside a block, and the snippet library, are never touched. Re-running init
    later adds a fresh block alongside what was kept.
    """
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    if global_scope:
        _eject_global(output, strip, yes)
        return

    root = _resolve_target(directory)
    plan = eject_module.plan_eject(root, strip=strip)
    if plan.malformed:
        raise AttentionError(eject_module.malformed_message(plan))
    if plan.is_empty:
        output.info("nothing to eject, this directory is not managed by mdcompose")
        return

    _run(output, plan, yes)


def _run(output: OutputContext, plan: eject_module.EjectPlan, yes: bool) -> None:
    for note in eject_module.summary(plan):
        output.warn(note)
    diff = eject_module.render_diff(plan)
    if diff:
        output.content(diff)
    if not _confirmed(output, yes):
        output.info("declined, nothing changed")
        return
    touched = eject_module.apply_eject(plan)
    output.info(f"ejected: {', '.join(touched)}" if touched else "nothing to change")


def _eject_global(output: OutputContext, strip: bool, yes: bool) -> None:
    """Eject the global pair and clear the mode and composition it recorded."""
    info = platform_module.detect_platform()
    config_directory = platform_module.config_dir()
    configuration = config_module.load_config(config_module.config_path(config_directory))
    claude_path = platform_module.resolve_global_claude_md(info).path
    agents_path = (
        None
        if configuration.global_agents_path is None
        else Path(configuration.global_agents_path).expanduser()
    )

    target_paths = [
        (Path(entry.path).expanduser(), managed_block.AGENTS_COMPOSITION_BLOCK)
        for entry in configuration.registered_global_targets
    ]
    changes = [
        _global_change(path, block_id, strip)
        for path, block_id in [
            (claude_path, managed_block.CLAUDE_MANAGED_BLOCK),
            (agents_path, managed_block.AGENTS_COMPOSITION_BLOCK),
            *target_paths,
        ]
        if path is not None
    ]
    malformed = [c for c in changes if c is None]
    real = [c for c in changes if c is not None]
    if malformed:
        raise AttentionError("a global file's markers are malformed; fix them before ejecting")

    modifies = [c for c in real if not files.content_equal(c[1], c[2])]
    recorded = (
        configuration.claude_global is not None
        or "global_snippet_ids" in configuration.extra
    )
    if not modifies and not recorded:
        output.info("nothing to eject, the global pair is not managed by mdcompose")
        return

    for name, before, after in modifies:
        output.content(_diff(name.name, before, after))
    if recorded:
        output.info("would clear the recorded global mode and composition from the config")
    if not _confirmed(output, yes):
        output.info("declined, nothing changed")
        return

    for path, _before, after in modifies:
        files.write_text(path, after, line_ending=files.line_ending_for(path))
    if recorded:
        extra = {k: v for k, v in configuration.extra.items() if k != "global_snippet_ids"}
        config_module.write_config(
            replace(configuration, claude_global=None, extra=extra),
            config_module.config_path(config_directory),
        )
    output.info("ejected the global pair")


def _global_change(
    path: Path, block_id: str, strip: bool
) -> tuple[Path, str, str] | None:
    if not files.path_exists(path) or not path.is_file():
        return (path, "", "")
    text = files.read_text(path)
    if managed_block.scan(text).problem is not None:
        return None
    return (path, text, managed_block.remove(text, block_id, path, keep_content=not strip))


def _diff(name: str, before: str, after: str) -> str:
    return eject_module.file_diff(name, before, after)


def _resolve_target(directory: Path | None) -> Path:
    root = Path.cwd() if directory is None else Path(directory).expanduser()
    if not root.is_dir():
        raise AttentionError(f"{root}: not a directory")
    return root


def _confirmed(output: OutputContext, yes: bool) -> bool:
    if yes:
        return True
    if output.json_mode or not is_interactive():
        raise AttentionError(
            "eject deletes the manifest and edits managed files. Re-run with --yes to "
            "apply the diff shown above."
        )
    return typer.confirm("apply this eject?", default=False, err=True)
