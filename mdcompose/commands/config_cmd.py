"""The config command group: show, set, unset, edit.

The write half of a capability change 1 left half-built. Reading the config
already existed; these commands are the way to change it without hand-editing a
JSON file whose location the user would have to work out from `doctor`.

Every write goes through `config.write_config`, which validates nothing itself:
validation is `config.apply_set`'s job and runs before the file is touched, so a
rejected value cannot corrupt the config.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from mdcompose.core import config as config_module
from mdcompose.core import files
from mdcompose.core import platform as platform_module
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.output import OutputContext
from mdcompose.prompts import output_for

app = typer.Typer(
    name="config",
    help="Show and change the global configuration.",
    rich_markup_mode=None,
    no_args_is_help=True,
)

QuietOption = Annotated[bool, typer.Option("--quiet", "-q", help="Suppress informational output.")]
NoColourOption = Annotated[bool, typer.Option("--no-color", help="Never colourize output.")]


def _resolve() -> tuple[Path, Path]:
    directory = platform_module.config_dir()
    return directory, config_module.config_path(directory)


@app.command("show")
def show(
    context: typer.Context,
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Print every recognized field, its effective value, and where the value came from.

    Creates nothing. With no config file, every field prints its default or
    not-configured state and the exit code is 0.
    """
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    directory, path = _resolve()
    configuration = config_module.load_config(path)
    present = "present" if files.path_exists(path) else "absent"
    output.info(f"config file  {path.as_posix()}  {present}")

    views = config_module.describe(configuration, directory)
    key_width = max(len(view.key) for view in views)
    state_width = max(len(view.state) for view in views)
    for view in views:
        output.info(f"  {view.key.ljust(key_width)}  {view.state.ljust(state_width)}  {view.value}")


@app.command("set")
def set_value(
    context: typer.Context,
    key: Annotated[str, typer.Argument(help="Field to set, dotted for a nested field.")],
    value: Annotated[str, typer.Argument(help="New value.")],
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Validate a value against the field's schema, then write it.

    A dotted key addresses a nested field. An invalid value, an unknown key, and
    schema_version are each refused before the file is touched.
    """
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    _, path = _resolve()
    configuration = config_module.load_config(path)
    updated = config_module.apply_set(configuration, key, value)
    if config_module.is_path_key(key):
        _warn_windows_mount(output, value)
    config_module.write_config(updated, path)
    output.info(f"set {key}")


@app.command("unset")
def unset_value(
    context: typer.Context,
    key: Annotated[str, typer.Argument(help="Field to remove, dotted for a nested field.")],
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Remove an explicitly set field so it falls back to its default or to unset.

    A field that is already absent is a no-op: the file is left unchanged and the
    exit code is 0. An unknown key is refused.
    """
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    _, path = _resolve()
    configuration = config_module.load_config(path)
    if not config_module.is_set(configuration, key):
        config_module.apply_unset(configuration, key)  # raises on an unknown key
        output.info(f"{key} was not set")
        return
    config_module.write_config(config_module.apply_unset(configuration, key), path)
    output.info(f"unset {key}")


@app.command("edit")
def edit(
    context: typer.Context,
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Open the config in the configured editor, validating the result before installing it.

    With no config file, the editor opens on the current defaults. An edit that
    is not valid JSON or violates the schema is refused and the existing config
    is left byte-identical.
    """
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    _, path = _resolve()
    original = files.read_text(path) if files.path_exists(path) else config_module.render(
        config_module.GlobalConfig()
    )
    edited = _edit_in_editor(original, path.name)
    if edited is None or files.content_equal(edited, original):
        output.info("config unchanged")
        return
    validated = config_module.load_config_text(edited, path)
    config_module.write_config(validated, path)
    output.info(f"wrote {path.as_posix()}")


def _edit_in_editor(seed: str, name: str) -> str | None:
    """Open a copy of ``seed`` in the editor and return the result, or None if unchanged."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        raise AttentionError(
            "no editor configured. Set VISUAL or EDITOR, or use 'config set' to change "
            "one field at a time."
        )
    with tempfile.TemporaryDirectory() as scratch:
        draft = Path(scratch) / name
        files.write_text(draft, seed)
        completed = subprocess.run([*shlex.split(editor), str(draft)], check=False)
        if completed.returncode != 0:
            raise AttentionError(f"editor exited with status {completed.returncode}")
        result = files.read_text(draft)
    return None if result == seed else result


def _warn_windows_mount(output: OutputContext, raw_value: str) -> None:
    """Warn when a path field is set to a location across the WSL and Windows boundary.

    Checked against the value the user typed, not the stored expansion: on
    Windows the expansion of a ``/mnt/`` path is not itself under ``/mnt/``.
    """
    info = platform_module.detect_platform()
    if platform_module.is_on_windows_mount(Path(raw_value), info):
        output.warn(
            f"{raw_value} is on a Windows drive mounted under "
            f"{platform_module.WINDOWS_MOUNT_PREFIX}, which crosses the WSL and Windows "
            "filesystem boundary"
        )
