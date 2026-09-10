"""The target command group: add, list, remove.

A target is a tool-specific global location the canonical global AGENTS.md is
projected into. These commands own the ``registered_global_targets`` config
field; ``config set`` refuses it because its uniqueness and absoluteness rules
cannot be enforced from a single key and value.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from mdcompose.core import config as config_module
from mdcompose.core import files, managed_block
from mdcompose.core import platform as platform_module
from mdcompose.core import targets as targets_module
from mdcompose.core.exit_codes import AttentionError
from mdcompose.prompts import output_for

app = typer.Typer(
    name="target",
    help="Register tool-specific global locations for projection.",
    rich_markup_mode=None,
    no_args_is_help=True,
)

QuietOption = Annotated[bool, typer.Option("--quiet", "-q", help="Suppress informational output.")]
JsonOption = Annotated[
    bool, typer.Option("--json", help="Emit one JSON document on stdout and nothing else.")
]
NoColourOption = Annotated[bool, typer.Option("--no-color", help="Never colourize output.")]


def _config() -> tuple[Path, config_module.GlobalConfig]:
    path = config_module.config_path(platform_module.config_dir())
    return path, config_module.load_config(path)


@app.command("add")
def add(
    context: typer.Context,
    label: Annotated[str, typer.Argument(help="A short name for the target.")],
    path: Annotated[str, typer.Argument(help="Absolute path of the tool's global file.")],
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Register a tool-specific global location. Writes no file at the path."""
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    config_path, configuration = _config()
    updated = targets_module.add_target(configuration, label, path)
    entry = updated.registered_global_targets[-1]
    info = platform_module.detect_platform()
    if platform_module.is_on_windows_mount(Path(entry.path), info):
        output.warn(
            f"{entry.path} is on a Windows drive mounted under "
            f"{platform_module.WINDOWS_MOUNT_PREFIX}, which crosses the WSL and Windows "
            "filesystem boundary"
        )
    config_module.write_config(updated, config_path)
    output.info(f"registered '{label}' at {entry.path}")


@app.command("remove")
def remove(
    context: typer.Context,
    label: Annotated[str, typer.Argument(help="The target to unregister.")],
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Unregister a target. Its file is left exactly where it is."""
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    config_path, configuration = _config()
    updated = targets_module.remove_target(configuration, label)  # raises on an unknown label
    existing = next(t for t in configuration.registered_global_targets if t.label == label)
    config_module.write_config(updated, config_path)
    output.info(
        f"unregistered '{label}'. Its file at {existing.path} was left in place; "
        "delete it by hand if you no longer need it."
    )


@app.command("list")
def list_targets(
    context: typer.Context,
    quiet: QuietOption = False,
    json_output: JsonOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Show every registered target, its path, and whether its file is in sync."""
    output = output_for(context, quiet=quiet, json_output=json_output, no_colour=no_colour)
    _, configuration = _config()
    canonical = _canonical_content(configuration)
    rows = [
        {
            "label": entry.label,
            "path": targets_module.target_path(entry).as_posix(),
            "present": files.path_exists(targets_module.target_path(entry)),
            "sync": (
                "unknown"
                if canonical is None
                else targets_module.sync_status(entry, canonical)
            ),
        }
        for entry in configuration.registered_global_targets
    ]

    if output.json_mode:
        output.emit(json.dumps({"targets": rows}, indent=2, ensure_ascii=True))
        return
    if not rows:
        output.info("no targets registered")
        return
    width = max(len(row["label"]) for row in rows)
    for row in rows:
        present = "present" if row["present"] else "absent"
        output.info(f"  {row['label'].ljust(width)}  {row['sync']:12}  {present}  {row['path']}")


def _canonical_content(configuration: config_module.GlobalConfig) -> str | None:
    """The composed content of the canonical global AGENTS.md, or None when unresolvable."""
    if configuration.global_agents_path is None:
        return None
    path = Path(configuration.global_agents_path).expanduser()
    if not (files.path_exists(path) and path.is_file()):
        return None
    block = managed_block.scan(files.read_text(path)).find(targets_module.TARGET_BLOCK)
    return None if block is None else block.content


def canonical_content_or_raise(configuration: config_module.GlobalConfig) -> str:
    """The canonical content, raising when the path is unset but targets exist."""
    content = _canonical_content(configuration)
    if content is None:
        raise AttentionError(
            "targets are registered but the canonical global AGENTS.md is not set or "
            "not composed. Run 'mdcompose init --global' first."
        )
    return content
