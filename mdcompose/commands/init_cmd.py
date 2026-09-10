"""The init command: compose a directory's AGENTS.md and CLAUDE.md.

The first command that modifies files the user already had. Everything it could
ask about is decided before anything is written, so a declined prompt leaves the
directory untouched rather than half-composed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from mdcompose.core import composition, files, init_ops, managed_block
from mdcompose.core import config as config_module
from mdcompose.core import manifest as manifest_module
from mdcompose.core import platform as platform_module
from mdcompose.core import snippets as snippets_module
from mdcompose.core.config import Mode
from mdcompose.core.exit_codes import EXIT_ATTENTION, AttentionError
from mdcompose.core.output import OutputContext
from mdcompose.core.snippets import Snippet
from mdcompose.prompts import confirm, is_interactive, output_for, prompt_choice

DirectoryArgument = Annotated[
    Path | None,
    typer.Argument(help="Directory to compose. Defaults to the current directory."),
]
ModeOption = Annotated[
    str | None,
    typer.Option("--mode", help="How CLAUDE.md relates to AGENTS.md: import or copy."),
]
SnippetsOption = Annotated[
    str | None,
    typer.Option("--snippets", help="Comma-separated snippet ids. Skips the picker."),
]
AcceptOption = Annotated[
    bool,
    typer.Option("--yes", "-y", help="Accept the stack-detected snippets and every prompt."),
]
OnDriftOption = Annotated[
    str | None,
    typer.Option("--on-drift", help="Resolve drift without asking: keep, overwrite, or abort."),
]
AgentsFromOption = Annotated[
    str | None,
    typer.Option(
        "--agents-from",
        help="Import an AGENTS.md from elsewhere instead of composing one here.",
    ),
]
GlobalOption = Annotated[
    bool, typer.Option("--global", help="Compose the global file pair instead.")
]
ReapplyOption = Annotated[
    bool,
    typer.Option(
        "--reapply",
        help="Re-compose from the recorded selection and mode without opening the picker.",
    ),
]
GlobalAgentsPathOption = Annotated[
    str | None,
    typer.Option(
        "--global-agents-path",
        help="Where the canonical global AGENTS.md lives. Asked once, then remembered.",
    ),
]
QuietOption = Annotated[bool, typer.Option("--quiet", "-q", help="Suppress informational output.")]
NoColourOption = Annotated[bool, typer.Option("--no-color", help="Never colourize output.")]


def register(app: typer.Typer) -> None:
    """Attach the command to an app, avoiding an import cycle with the CLI module."""
    app.command("init")(init)


def init(
    context: typer.Context,
    directory: DirectoryArgument = None,
    mode: ModeOption = None,
    snippet_ids: SnippetsOption = None,
    accept: AcceptOption = False,
    on_drift: OnDriftOption = None,
    agents_from: AgentsFromOption = None,
    global_scope: GlobalOption = False,
    global_agents_path: GlobalAgentsPathOption = None,
    reapply: ReapplyOption = False,
    quiet: QuietOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Compose AGENTS.md and CLAUDE.md from the snippet library.

    Re-running reopens the picker with the recorded selections already checked,
    rather than refusing. --reapply skips the picker and re-composes from what
    the manifest recorded. Every prompt has a flag, so the whole command runs
    unattended.
    """
    output = output_for(context, quiet=quiet, no_colour=no_colour)
    config_directory = platform_module.config_dir()
    configuration = config_module.load_config(config_module.config_path(config_directory))
    library = snippets_module.view(config_module.library_dir(configuration, config_directory))

    if global_scope:
        _init_global(
            output,
            configuration,
            config_directory,
            library,
            mode,
            snippet_ids,
            accept,
            global_agents_path,
        )
        return

    root = _resolve_target(directory)
    _warn_onedrive(output, (("config directory", config_directory), ("target directory", root)))
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(root))
    if library.is_empty and manifest is None:
        raise AttentionError(
            f"the snippet library at {library.directory.as_posix()} is empty, so there "
            "is nothing to compose. Add a snippet first."
        )
    if reapply and manifest is None:
        raise AttentionError(
            f"{root}: no mdcompose.lock here, so there is no recorded selection to re-apply"
        )
    _warn_bare_directory(output, root, manifest)

    interactive_ok = not reapply
    prepared = init_ops.plan(
        root=root,
        library=library,
        manifest=manifest,
        requested_ids=_parse_ids(snippet_ids),
        accept_detected=accept,
        requested_mode=_validated_mode(mode),
        default_mode=_default_mode(configuration, accept=accept),
        selector=_selector(output, accept) if interactive_ok else None,
        ask_mode=_mode_asker(output, accept) if interactive_ok else None,
        import_from=agents_from,
    )
    _refuse_malformed(prepared)
    _warn_empty_selection(output, prepared)
    _warn_redundant_import(output, prepared, root)
    if not _confirm_foreign(output, prepared, accept=accept):
        output.info("nothing written")
        return

    choices = _drift_choices(output, prepared, on_drift, accept=accept)
    if init_ops.ABORT in choices.values():
        output.info("aborted, nothing written")
        raise typer.Exit(EXIT_ATTENTION)

    result = init_ops.apply(
        prepared,
        generated_by=_generated_by(),
        drift_choices=choices,
    )
    _report(output, prepared, result)


def _resolve_target(directory: Path | None) -> Path:
    root = Path.cwd() if directory is None else Path(directory).expanduser()
    if root.is_dir():
        return root
    if directory is not None and _looks_like_a_snippet_id(str(directory)) and not root.exists():
        raise AttentionError(
            f"{root}: not a directory. If '{directory}' is a snippet id it belongs to "
            "--snippets, and a comma-separated list must be quoted so the shell keeps it "
            "as one argument (PowerShell splits an unquoted list on the comma)."
        )
    raise AttentionError(f"{root}: not a directory")


def _looks_like_a_snippet_id(candidate: str) -> bool:
    return "/" not in candidate and "\\" not in candidate and candidate not in {".", ".."}


def _parse_ids(raw: str | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _validated_mode(raw: str | None) -> Mode | None:
    if raw is None:
        return None
    if raw not in {composition.IMPORT, composition.COPY}:
        raise AttentionError(
            f"--mode must be '{composition.IMPORT}' or '{composition.COPY}', found '{raw}'"
        )
    return raw  # type: ignore[return-value]


def _generated_by() -> str:
    """The version string recorded in a manifest.

    Imported at call time because the CLI module registers this command, so a
    module-level import would be a cycle.
    """
    from mdcompose.cli import PACKAGE_NAME, resolve_version

    return f"{PACKAGE_NAME} {resolve_version()}"


def _default_mode(
    configuration: config_module.GlobalConfig, *, accept: bool
) -> Mode | None:
    """The mode to fall back on when nothing else answers.

    ``--yes`` means accept every prompt, and the mode question is a prompt, so it
    has to answer that one too. Without this a fully scripted first run would
    refuse for want of an answer the user had already given.
    """
    if configuration.default_mode is not None:
        return configuration.default_mode
    return composition.IMPORT if accept else None


def _selector(output: OutputContext, accept: bool) -> init_ops.Selector | None:
    """Return an interactive picker, or None when there is nobody to ask."""
    if accept or output.json_mode or not is_interactive():
        return None

    def pick(
        available: tuple[Snippet, ...], preselected: tuple[str, ...]
    ) -> tuple[str, ...]:
        return _run_picker(available, preselected)

    return pick


def _run_picker(
    available: tuple[Snippet, ...],
    preselected: tuple[str, ...],
) -> tuple[str, ...]:
    """Ask which snippets to compose, grouped by category.

    Imported here rather than at module level so the picker library is only
    loaded when a picker is actually opened, which keeps every non-interactive
    run free of it.
    """
    import questionary

    grouped: dict[str, list[Snippet]] = {}
    for snippet in available:
        grouped.setdefault(snippet.category or "uncategorized", []).append(snippet)

    choices: list[object] = []
    for category in sorted(grouped):
        choices.append(questionary.Separator(f"-- {category} --"))
        for snippet in grouped[category]:
            label = snippet.display_name
            if snippet.description is not None:
                label = f"{label}: {snippet.description}"
            choices.append(
                questionary.Choice(
                    title=label, value=snippet.id, checked=snippet.id in preselected
                )
            )

    answer = questionary.checkbox("Snippets to compose", choices=choices).ask()
    if answer is None:
        raise AttentionError("no selection made")
    return tuple(answer)


def _mode_asker(output: OutputContext, accept: bool):  # noqa: ANN202 - a closure or None
    """Return a callable that asks for the mode, or None when nobody can be asked."""
    if accept or output.json_mode or not is_interactive():
        return None

    def ask() -> Mode:
        answer = prompt_choice(
            output,
            "how should CLAUDE.md relate to AGENTS.md",
            options=(composition.IMPORT, composition.COPY),
            default=composition.IMPORT,
            flag="--mode",
        )
        return answer  # type: ignore[return-value]

    return ask


def _refuse_malformed(prepared: init_ops.InitPlan) -> None:
    """Stop before writing when a managed file's markers cannot be parsed.

    Harsher than drift on purpose: with drift the boundaries are known and only
    the content is unexpected, but a malformed file gives mdcompose no way to
    tell which bytes it owns, so any write risks destroying user content.
    """
    for entry in prepared.malformed:
        raise AttentionError(
            f"{entry.path}: {entry.detail}. Fix the markers before composing."
        )


def _warn_onedrive(output: OutputContext, labelled: tuple[tuple[str, Path], ...]) -> None:
    """Warn once per given path that sits inside a OneDrive-synced folder.

    A warning only, matching doctor: OneDrive breaks Files On-Demand reads and
    races a mdcompose.lock write, but the run is never blocked.
    """
    info = platform_module.detect_platform()
    for label, path in labelled:
        root = platform_module.onedrive_root_for(path, info)
        if root is not None:
            output.warn(platform_module.onedrive_warning(label, path, root))


def _warn_bare_directory(
    output: OutputContext, root: Path, manifest: manifest_module.Manifest | None
) -> None:
    """Say what init is about to do in a directory that has none of its files.

    No AGENTS.md, no CLAUDE.md, and no manifest very likely means this is not the
    directory the user meant. init still proceeds, because a first run in a fresh
    project looks exactly the same, but it no longer creates two files in silence.
    """
    if manifest is not None:
        return
    if files.path_exists(root / "AGENTS.md") or files.path_exists(root / "CLAUDE.md"):
        return
    output.warn(
        f"{root}: no AGENTS.md, CLAUDE.md, or mdcompose.lock here; "
        "init will create AGENTS.md and CLAUDE.md in this directory"
    )


def _warn_empty_selection(output: OutputContext, prepared: init_ops.InitPlan) -> None:
    """Say plainly when a run composes nothing, so an empty block is not a surprise."""
    if prepared.from_embedded or prepared.selection:
        return
    output.warn("no snippets selected; the managed blocks will be written empty")


def _warn_redundant_import(
    output: OutputContext, prepared: init_ops.InitPlan, root: Path
) -> None:
    """Point out an @import that already sits outside the block init will fill.

    In import mode init writes the import directive into CLAUDE.md's managed
    block. A copy of that directive the user placed elsewhere in the file is now
    redundant, and init leaves it alone because it owns only its own block.
    """
    if prepared.mode != composition.IMPORT or prepared.imports is None:
        return
    claude = root / "CLAUDE.md"
    if not files.path_exists(claude):
        return
    if not managed_block.read_blocks(claude).is_well_formed:
        return
    outside = managed_block.remove(
        files.read_text(claude),
        managed_block.CLAUDE_MANAGED_BLOCK,
        claude,
        keep_content=False,
    )
    directive = composition.import_directive(prepared.imports).strip()
    if any(line.strip() == directive for line in outside.split("\n")):
        output.warn(
            f"CLAUDE.md already has '{directive}' outside the managed block; "
            "that line is now redundant and init will not remove it"
        )


def _confirm_foreign(
    output: OutputContext, prepared: init_ops.InitPlan, *, accept: bool
) -> bool:
    """Show content that came from elsewhere, and ask before writing it.

    This is the trust boundary. A cloned manifest carries markdown somebody else
    wrote, about to land in a file an AI agent reads. Composing it silently would
    hide it at exactly the moment it should be visible.
    """
    if not prepared.from_embedded:
        return True

    output.info("this manifest was not composed on this machine. It would write:")
    for target in prepared.targets:
        output.info(f"  {target.relative_path}:")
        output.content(_indent(target.content))
    return confirm(
        output,
        "compose these files from the manifest?",
        assume_yes=accept,
        flag="--yes",
    )


def _indent(text: str) -> str:
    if not text.strip():
        return "    (empty)"
    return "\n".join(f"    {line}" for line in text.rstrip("\n").split("\n"))


def _drift_choices(
    output: OutputContext,
    prepared: init_ops.InitPlan,
    on_drift: str | None,
    *,
    accept: bool,
) -> dict[str, init_ops.DriftChoice]:
    """Decide what to do about every drifted file before writing any of them."""
    if not prepared.drifted:
        return {}
    if on_drift is not None:
        decision = _validated_drift_choice(on_drift)
        return {entry.key: decision for entry in prepared.drifted}
    if accept:
        return {entry.key: init_ops.OVERWRITE for entry in prepared.drifted}

    choices: dict[str, init_ops.DriftChoice] = {}
    for entry in prepared.drifted:
        target = prepared.target_for(entry.key)
        output.warn(f"{entry.path} has been edited by hand since mdcompose wrote it")
        _show_drift(output, target)
        answer = prompt_choice(
            output,
            f"{entry.path.name}",
            options=(init_ops.KEEP, init_ops.OVERWRITE, init_ops.ABORT),
            default=init_ops.KEEP,
            flag="--on-drift",
        )
        choices[entry.key] = answer  # type: ignore[assignment]
    return choices


def _show_drift(output: OutputContext, target: init_ops.FileTarget | None) -> None:
    """Show what is there against what would replace it."""
    if target is None:
        return
    result = managed_block.read_blocks(target.path)
    block = result.find(target.block_id)
    output.info("  currently:")
    output.content(_indent("" if block is None else block.content))
    output.info("  would become:")
    output.content(_indent(target.content))


def _validated_drift_choice(candidate: str) -> init_ops.DriftChoice:
    allowed = (init_ops.KEEP, init_ops.OVERWRITE, init_ops.ABORT)
    if candidate not in allowed:
        raise AttentionError(
            f"--on-drift must be one of {', '.join(allowed)}, found '{candidate}'"
        )
    return candidate  # type: ignore[return-value]


def _report(
    output: OutputContext, prepared: init_ops.InitPlan, result: init_ops.InitResult
) -> None:
    output.info(f"mode: {prepared.mode}")
    if prepared.detected_stack:
        output.info(f"detected: {', '.join(prepared.detected_stack)}")
    output.info(f"snippets: {', '.join(item.id for item in prepared.selection) or 'none'}")
    for label, keys in (
        ("wrote", result.written),
        ("unchanged", result.unchanged),
        ("kept your edits in", result.kept),
    ):
        if keys:
            output.info(f"  {label}: {', '.join(keys)}")
    if result.manifest_path is not None:
        output.info(f"  recorded in: {result.manifest_path.name}")


GLOBAL_AGENTS_CHOICES = ("~/.claude/AGENTS.md", "~/.codex/AGENTS.md")


def _init_global(
    output: OutputContext,
    configuration: config_module.GlobalConfig,
    config_directory: Path,
    library: snippets_module.LibraryView,
    mode: str | None,
    snippet_ids: str | None,
    accept: bool,
    global_agents_path: str | None,
) -> None:
    """Compose the global file pair, recording its state in the global config.

    The same composition machinery as a project, pointed at two different paths.
    Its mode and selection go in the config rather than a manifest, because there
    is no manifest for a home directory and inventing one would put
    project-shaped state somewhere nobody would look for it.
    """
    if library.is_empty:
        raise AttentionError(
            f"the snippet library at {library.directory.as_posix()} is empty, so there "
            "is nothing to compose."
        )

    agents_path = _resolve_global_agents_path(
        output, configuration, global_agents_path, accept=accept
    )
    claude_path = platform_module.resolve_global_claude_md(
        platform_module.detect_platform()
    ).path
    _warn_onedrive(
        output,
        (
            ("config directory", config_directory),
            ("global AGENTS.md", agents_path),
            ("global CLAUDE.md", claude_path),
        ),
    )

    claude_global = configuration.claude_global
    recorded_mode = None if claude_global is None else claude_global.mode
    resolved_mode = init_ops.resolve_mode(
        requested=_validated_mode(mode),
        recorded=recorded_mode,
        default=_default_mode(configuration, accept=accept),
        ask=_mode_asker(output, accept),
    )
    selection = _global_selection(library, configuration, snippet_ids, accept, output)
    composed = composition.compose(
        selection,
        mode=resolved_mode,
        import_target=init_ops._relative_posix(agents_path, claude_path.parent),
    )

    wrote = []
    if composition.apply_to_file(
        agents_path, managed_block.AGENTS_COMPOSITION_BLOCK, composed.agents_block
    ):
        wrote.append(agents_path.as_posix())
    if composition.apply_to_file(
        claude_path, managed_block.CLAUDE_MANAGED_BLOCK, composed.claude_block
    ):
        wrote.append(claude_path.as_posix())

    config_module.write_config(
        _recorded_global_config(configuration, agents_path, claude_path, resolved_mode, composed),
        config_module.config_path(config_directory),
    )
    output.info(f"mode: {resolved_mode}")
    output.info(f"snippets: {', '.join(item.id for item in selection) or 'none'}")
    for path in wrote:
        output.info(f"  wrote: {path}")
    if not wrote:
        output.info("  unchanged")

    recorded = _recorded_global_config(
        configuration, agents_path, claude_path, resolved_mode, composed
    )
    _project_to_targets(output, recorded, composed.agents_block, accept)


def _project_to_targets(
    output: OutputContext,
    configuration: config_module.GlobalConfig,
    canonical_content: str,
    accept: bool,
) -> None:
    """Project the canonical AGENTS.md content into every registered target.

    Failures are isolated: one bad target does not stop the others, and the run
    reports a non-zero outcome so the condition is not swallowed.
    """
    from mdcompose.core import targets as targets_module

    if not configuration.registered_global_targets:
        return
    drifted = targets_module.drifted_targets(configuration, canonical_content)
    choices: dict[str, targets_module.DriftChoice] = {}
    if drifted:
        decision = _target_drift_decision(output, drifted, accept)
        choices = {entry.label: decision for entry in drifted}

    result = targets_module.project(configuration, canonical_content, drift_choices=choices)
    for outcome in result.outcomes:
        if outcome.status in {"written", "created"}:
            output.info(f"  projected: {outcome.label}")
        elif outcome.status == "kept":
            output.warn(f"  {outcome.label}: {outcome.detail}")
        elif outcome.status.startswith("skipped"):
            output.warn(f"  {outcome.label}: {outcome.detail}, skipped")
    if result.had_failure:
        raise typer.Exit(EXIT_ATTENTION)


def _target_drift_decision(
    output: OutputContext, drifted: tuple, accept: bool
) -> str:
    from mdcompose.core import targets as targets_module

    if accept:
        return targets_module.OVERWRITE
    names = ", ".join(entry.label for entry in drifted)
    return prompt_choice(
        output,
        f"targets edited by hand ({names})",
        options=targets_module.DRIFT_CHOICES,
        default=targets_module.KEEP,
        flag="--yes",
    )


def _resolve_global_agents_path(
    output: OutputContext,
    configuration: config_module.GlobalConfig,
    supplied: str | None,
    *,
    accept: bool,
) -> Path:
    """Decide where the canonical global AGENTS.md lives, asking only once.

    Chosen lazily: only a command that writes the global pair asks, and the
    answer is recorded so it is never asked again.
    """
    chosen = supplied or configuration.global_agents_path
    if chosen is None:
        chosen = (
            GLOBAL_AGENTS_CHOICES[0]
            if accept
            else prompt_choice(
                output,
                "where should the canonical global AGENTS.md live",
                options=GLOBAL_AGENTS_CHOICES,
                default=GLOBAL_AGENTS_CHOICES[0],
                flag="--global-agents-path",
            )
        )
    resolved = Path(chosen).expanduser()
    if resolved.is_dir():
        raise AttentionError(f"{resolved}: is a directory, not a file")
    return resolved


def _global_selection(
    library: snippets_module.LibraryView,
    configuration: config_module.GlobalConfig,
    snippet_ids: str | None,
    accept: bool,
    output: OutputContext,
) -> tuple[Snippet, ...]:
    """Which snippets the global pair composes."""
    requested = _parse_ids(snippet_ids)
    if requested is not None:
        return tuple(library.require(item) for item in requested)
    recorded = _recorded_global_ids(configuration)
    selector = _selector(output, accept)
    if selector is None:
        if recorded:
            return tuple(library.require(item) for item in recorded)
        raise AttentionError(
            "no snippet selection was supplied and there is no terminal to open the "
            "picker on. Pass --snippets with a comma-separated list."
        )
    return tuple(library.require(item) for item in selector(library.snippets, recorded))


def _recorded_global_ids(configuration: config_module.GlobalConfig) -> tuple[str, ...]:
    recorded = configuration.extra.get("global_snippet_ids")
    if isinstance(recorded, list) and all(isinstance(item, str) for item in recorded):
        return tuple(recorded)
    return ()


def _recorded_global_config(
    configuration: config_module.GlobalConfig,
    agents_path: Path,
    claude_path: Path,
    mode: Mode,
    composed: composition.Composition,
) -> config_module.GlobalConfig:
    extra = dict(configuration.extra)
    extra["global_snippet_ids"] = list(composed.snippet_ids)
    return config_module.GlobalConfig(
        schema_version=configuration.schema_version or config_module.SCHEMA_VERSION,
        snippet_library_path=configuration.snippet_library_path,
        default_mode=configuration.default_mode,
        claude_global=config_module.ClaudeGlobal(path=claude_path.as_posix(), mode=mode),
        global_agents_path=agents_path.as_posix(),
        registered_global_targets=configuration.registered_global_targets,
        extra=extra,
        source=configuration.source,
    )
