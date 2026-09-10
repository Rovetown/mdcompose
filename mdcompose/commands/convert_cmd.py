"""The convert command: move unmanaged content between AGENTS.md and CLAUDE.md.

`convert` moves the sections a user wrote into the wrong file: Claude-only prose
that belongs in the shared AGENTS.md, or the reverse. It reads and writes only
content outside managed blocks, so it never overlaps with `init`. The content is
removed from the source once the target write succeeds, which is why every run
shows a diff and asks before writing.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from mdcompose.commands.import_cmd import _picker as _section_picker
from mdcompose.core import composition, convert_ops, files, import_ops, init_ops, managed_block
from mdcompose.core import config as config_module
from mdcompose.core import manifest as manifest_module
from mdcompose.core import platform as platform_module
from mdcompose.core.config import Mode
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.output import OutputContext
from mdcompose.core.sections import Section
from mdcompose.prompts import is_interactive, output_for, prompt_choice

SourceArgument = Annotated[
    str, typer.Argument(help="File to move content out of: AGENTS.md or CLAUDE.md.")
]
TargetArgument = Annotated[
    str, typer.Argument(help="File to move content into: the other of the pair.")
]
SectionOption = Annotated[
    list[str] | None,
    typer.Option(
        "--section", help="Move the section with this heading. Repeatable. Bypasses the picker."
    ),
]
ModeOption = Annotated[
    str | None,
    typer.Option("--mode", help="How a new CLAUDE.md block relates to AGENTS.md: import or copy."),
]
YesOption = Annotated[
    bool, typer.Option("--yes", "-y", help="Confirm the conversion without a prompt.")
]
QuietOption = Annotated[bool, typer.Option("--quiet", "-q", help="Suppress informational output.")]
NoColourOption = Annotated[bool, typer.Option("--no-color", help="Never colourize output.")]


def register(app: typer.Typer) -> None:
    """Attach the command to an app under its real name."""
    app.command("convert")(convert_files)


def convert_files(
    context: typer.Context,
    source: SourceArgument,
    target: TargetArgument,
    section_names: SectionOption = None,
    mode: ModeOption = None,
    yes: YesOption = False,
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Move chosen sections of one project file into the other, outside its block.

    The moved content leaves the source and lands in the target's user-owned
    region, so a later `init` neither overwrites nor removes it. --mode applies
    only when the target is a CLAUDE.md with no managed block, since creating one
    means deciding what it holds.
    """
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    info = platform_module.detect_platform()
    source_path, target_path = _resolve_pair(source, target, info)
    convert_ops.require_different(source_path, target_path)

    project_root = Path.cwd()
    requested_mode = _validated_mode(mode)
    _reject_mode_where_it_cannot_apply(target_path, requested_mode)

    source_text = files.read_text(source_path)
    available = convert_ops.unmanaged_sections(source_text, source_path)
    if _nothing_convertible(available):
        output.info("nothing to convert, the source has no content outside a managed block")
        return

    names = tuple(section_names or ())
    selected = import_ops.resolve_selection(
        available, requested_headings=names or None, selector=_section_picker(output)
    )
    if not selected:
        output.info("nothing selected, nothing converted")
        return

    new_block_mode = _new_block_mode(output, target_path, project_root, requested_mode)
    target_text = files.read_text(target_path) if target_path.is_file() else ""
    plan = convert_ops.plan_conversion(
        source_path,
        target_path,
        moved=selected,
        source_text=source_text,
        target_text=target_text,
        new_block_mode=new_block_mode,
    )
    diff = convert_ops.render_diff(plan)
    if diff:
        output.content(diff)
    if not _confirmed(output, yes):
        output.info("declined, nothing converted")
        return

    convert_ops.apply_conversion(plan)
    if new_block_mode is not None:
        _record_mode(project_root, target_path, new_block_mode)
    plural = "" if len(selected) == 1 else "s"
    output.info(
        f"moved {len(selected)} section{plural} from {source_path.name} to {target_path.name}"
    )


def _validated_mode(raw: str | None) -> Mode | None:
    if raw is None:
        return None
    if raw not in {composition.IMPORT, composition.COPY}:
        raise AttentionError(
            f"--mode must be '{composition.IMPORT}' or '{composition.COPY}', found '{raw}'"
        )
    return raw


def _reject_mode_where_it_cannot_apply(target_path: Path, requested: Mode | None) -> None:
    """--mode is rejected, not ignored, everywhere it cannot apply.

    It applies only when creating a claude-managed block: a CLAUDE.md target with
    no block yet. On AGENTS.md, or a CLAUDE.md that already has a block, supplying
    it means the user expected something that will not happen.
    """
    if requested is None:
        return
    if target_path.name != platform_module.CLAUDE_MD_NAME:
        raise AttentionError("--mode does not apply to AGENTS.md, which is always plain markdown")
    if _has_claude_block(target_path):
        raise AttentionError(
            "CLAUDE.md already has a managed block; a mode change belongs to init, not convert"
        )


def _has_claude_block(target_path: Path) -> bool:
    return (
        target_path.is_file()
        and managed_block.read_blocks(target_path).find(managed_block.CLAUDE_MANAGED_BLOCK)
        is not None
    )


def _new_block_mode(
    output: OutputContext,
    target_path: Path,
    project_root: Path,
    requested: Mode | None,
) -> Mode | None:
    """The mode for a claude-managed block this run would create, or None.

    Only a CLAUDE.md target with no block yet needs one. Precedence follows
    `init`: an explicit flag, then the recorded project mode, then the configured
    default, then a question, then a refusal naming the flag.
    """
    if target_path.name != platform_module.CLAUDE_MD_NAME or _has_claude_block(target_path):
        return None

    configuration = config_module.load_config(
        config_module.config_path(platform_module.config_dir())
    )
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(project_root))
    recorded = None
    entry = None if manifest is None else manifest.files.get(manifest_module.CLAUDE_MD_KEY)
    if entry is not None:
        recorded = entry.mode
    return init_ops.resolve_mode(
        requested=requested,
        recorded=recorded,
        default=configuration.default_mode,
        ask=_mode_asker(output),
    )


def _mode_asker(output: OutputContext) -> Callable[[], Mode] | None:
    if output.json_mode or not is_interactive():
        return None

    def ask() -> Mode:
        answer = prompt_choice(
            output,
            "the target CLAUDE.md needs a managed block; how should it relate to AGENTS.md",
            options=(composition.IMPORT, composition.COPY),
            default=composition.IMPORT,
            flag="--mode",
        )
        return answer  # type: ignore[return-value]

    return ask


def _record_mode(project_root: Path, target_path: Path, mode: Mode) -> None:
    """Record the created block's mode, updating the manifest or writing a new one."""
    block = managed_block.read_blocks(target_path).find(managed_block.CLAUDE_MANAGED_BLOCK)
    block_hash = files.hash_content("" if block is None else block.content)
    imports = "AGENTS.md" if mode == composition.IMPORT else None
    entry = manifest_module.FileEntry(
        path=platform_module.CLAUDE_MD_NAME,
        mode=mode,
        managed_block_hash=block_hash,
        imports=imports,
    )
    path = manifest_module.manifest_path(project_root)
    manifest = manifest_module.load_manifest(path)
    if manifest is None:
        from mdcompose.cli import PACKAGE_NAME, resolve_version

        built = manifest_module.build(
            generated_by=f"{PACKAGE_NAME} {resolve_version()}",
            generated_at=_now(),
            detected_stack=(),
            snippets=(),
            files_recorded={manifest_module.CLAUDE_MD_KEY: entry},
            source=path,
        )
    else:
        files_recorded = dict(manifest.files)
        files_recorded[manifest_module.CLAUDE_MD_KEY] = entry
        built = manifest_module.build(
            generated_by=manifest.generated_by or "",
            generated_at=manifest.generated_at or _now(),
            detected_stack=manifest.detected_stack,
            snippets=manifest.snippets_in_order(),
            files_recorded=files_recorded,
            source=path,
        )
    manifest_module.write_manifest(built, path)


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _resolve_pair(
    source: str, target: str, info: platform_module.PlatformInfo
) -> tuple[Path, Path]:
    """Resolve both arguments to the project's own AGENTS.md or CLAUDE.md."""
    project = Path.cwd()
    supported = {
        files.normalized_path(project / platform_module.AGENTS_MD_NAME): project
        / platform_module.AGENTS_MD_NAME,
        files.normalized_path(project / platform_module.CLAUDE_MD_NAME): project
        / platform_module.CLAUDE_MD_NAME,
    }
    source_path = _one_of(source, info, supported)
    target_path = _one_of(target, info, supported)
    if not source_path.is_file():
        raise AttentionError(f"{source_path}: no such file to convert from")
    return source_path, target_path


def _one_of(
    raw: str, info: platform_module.PlatformInfo, supported: dict[str, Path]
) -> Path:
    resolved = platform_module.resolve_path(raw, info)
    match = supported.get(files.normalized_path(resolved.path))
    if match is None:
        raise AttentionError(
            f"{resolved.path}: convert operates on this project's AGENTS.md and CLAUDE.md, "
            "nothing else"
        )
    return match


def _nothing_convertible(available: tuple[Section, ...]) -> bool:
    if not available:
        return True
    return all(section.synthetic and not section.content.strip() for section in available)


def _confirmed(output: OutputContext, yes: bool) -> bool:
    """Confirm the conversion after the diff, refusing to guess with nobody to ask.

    The diff is always printed first, by the caller, so a scripted run with --yes
    still records what changed.
    """
    if yes:
        return True
    if output.json_mode or not is_interactive():
        raise AttentionError(
            "convert moves content between both files. Re-run with --yes to apply the "
            "diff shown above."
        )
    return typer.confirm("apply this conversion?", default=False, err=True)
