"""Orchestration for init: decide everything, then write.

Planning and writing are separate on purpose. The plan answers every question
that needs answering, including which files have drifted and whether the manifest
came from somewhere else, before a single byte is written. That is what lets the
CLI ask the user once, up front, rather than one question per file mid-write, and
it is what makes an abort leave nothing half-done.

Every decision the user could be asked for arrives here as an argument. A flag
and an answered prompt therefore reach identical code, which is how the
scriptability rule holds mechanically rather than by discipline.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from mdcompose.core import composition, files, managed_block, platform
from mdcompose.core import manifest as manifest_module
from mdcompose.core.config import Mode
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.snippets import LibraryView, Snippet

DriftChoice = Literal["keep", "overwrite", "abort"]

KEEP: DriftChoice = "keep"
OVERWRITE: DriftChoice = "overwrite"
ABORT: DriftChoice = "abort"
DRIFT_CHOICES: tuple[DriftChoice, ...] = (KEEP, OVERWRITE, ABORT)

#: How a selection was arrived at, so a command can say what it did.
SelectionSource = Literal["flag", "detected", "picker", "manifest", "embedded"]

#: Chooses snippets. The CLI supplies an interactive picker, a test supplies a
#: stub. Keeping this a plain callable is what stops the picker library from
#: reaching into core.
Selector = Callable[[tuple[Snippet, ...], tuple[str, ...]], tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class FileTarget:
    """One managed file: where it is, which block it owns, what goes in it."""

    key: str
    path: Path
    block_id: str
    content: str
    relative_path: str


@dataclass(frozen=True, slots=True)
class InitPlan:
    """Everything decided before anything is written."""

    root: Path
    mode: Mode
    selection: tuple[Snippet, ...]
    selection_source: SelectionSource
    detected_stack: tuple[str, ...]
    targets: tuple[FileTarget, ...]
    drift: tuple[manifest_module.FileDrift, ...]
    imports: str | None
    from_embedded: bool

    @property
    def drifted(self) -> tuple[manifest_module.FileDrift, ...]:
        return tuple(item for item in self.drift if item.status == manifest_module.DRIFTED)

    @property
    def malformed(self) -> tuple[manifest_module.FileDrift, ...]:
        return tuple(item for item in self.drift if item.status == manifest_module.MALFORMED)

    @property
    def needs_composing_from_embedded(self) -> bool:
        """Whether the manifest describes files this machine has not composed."""
        return any(
            item.status in {manifest_module.MISSING, manifest_module.BLOCK_REMOVED}
            for item in self.drift
        )

    def target_for(self, key: str) -> FileTarget | None:
        for target in self.targets:
            if target.key == key:
                return target
        return None


@dataclass(frozen=True, slots=True)
class InitResult:
    """What was actually written."""

    written: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    kept: tuple[str, ...] = ()
    manifest_path: Path | None = None
    extra: Mapping[str, object] = field(default_factory=dict)


def resolve_selection(
    library: LibraryView,
    *,
    manifest: manifest_module.Manifest | None,
    requested_ids: tuple[str, ...] | None,
    detected_ids: tuple[str, ...],
    accept_detected: bool,
    selector: Selector | None,
) -> tuple[tuple[Snippet, ...], SelectionSource]:
    """Work out which snippets to compose, and say how that was decided.

    Order of precedence: an explicit list, then accepting the detected set, then
    the picker seeded with whatever is already recorded. Recorded selections beat
    detection, because a snippet the user unchecked must not be re-checked on
    every run: a tool that argues with the user is worse than one that guesses
    wrong once.
    """
    if requested_ids is not None:
        return _snippets_for(library, requested_ids), "flag"
    if accept_detected:
        return _snippets_for(library, detected_ids), "detected"

    recorded = _recorded_ids(manifest)
    preselected = recorded if recorded is not None else detected_ids
    if selector is None:
        if recorded is not None:
            return _snippets_for(library, recorded), "manifest"
        raise AttentionError(
            "no snippet selection was supplied and there is no terminal to open the "
            "picker on. Pass --snippets with a comma-separated list, or --yes to "
            "accept the detected suggestions."
        )
    chosen = selector(library.snippets, preselected)
    return _snippets_for(library, tuple(chosen)), "picker"


def _recorded_ids(manifest: manifest_module.Manifest | None) -> tuple[str, ...] | None:
    if manifest is None:
        return None
    return tuple(entry.id for entry in manifest.snippets_in_order())


def _snippets_for(library: LibraryView, ids: tuple[str, ...]) -> tuple[Snippet, ...]:
    """Resolve ids against the library, naming every one that is unknown."""
    unknown = [candidate for candidate in ids if library.find(candidate) is None]
    if unknown:
        listed = ", ".join(f"'{item}'" for item in unknown)
        available = ", ".join(item.id for item in library.snippets) or "none"
        raise AttentionError(
            f"no snippet named {listed} in the library. Available: {available}"
        )
    return tuple(library.require(candidate) for candidate in ids)


def snippets_from_manifest(manifest: manifest_module.Manifest) -> tuple[Snippet, ...]:
    """Build a selection from a manifest's embedded content.

    Used on the clone path, where the local library may be empty. The content
    travels with the manifest precisely so this works without one.
    """
    return tuple(
        Snippet(id=entry.id, body=entry.content, applies_to=_applies_to(entry.applies_to))
        for entry in manifest.snippets_in_order()
    )


def _applies_to(value: str) -> Literal["agents", "claude", "both"]:
    return value if value in {"agents", "claude", "both"} else "both"  # type: ignore[return-value]


def resolve_mode(
    *,
    requested: Mode | None,
    recorded: Mode | None,
    default: Mode | None,
    ask: Callable[[], Mode] | None,
) -> Mode:
    """Decide the mode, asking only when nothing else answers.

    A flag wins, then whatever was recorded last time, then the configured
    default, then a question. Asked once per pair and remembered, so later runs
    do not re-ask.
    """
    if requested is not None:
        return requested
    if recorded is not None:
        return recorded
    if ask is not None:
        return ask()
    if default is not None:
        return default
    raise AttentionError(
        "no mode was supplied and there is no terminal to ask on. "
        f"Pass --mode with '{composition.IMPORT}' or '{composition.COPY}'."
    )


def plan(
    *,
    root: Path,
    library: LibraryView,
    manifest: manifest_module.Manifest | None,
    requested_ids: tuple[str, ...] | None = None,
    accept_detected: bool = False,
    requested_mode: Mode | None = None,
    default_mode: Mode | None = None,
    selector: Selector | None = None,
    ask_mode: Callable[[], Mode] | None = None,
    import_from: str | None = None,
) -> InitPlan:
    """Decide everything init would do, without touching a single file."""
    detected_stack, suggested_ids = _detect(root, library)
    drift = () if manifest is None else manifest_module.detect_drift(manifest, root)
    from_embedded = manifest is not None and any(
        item.status in {manifest_module.MISSING, manifest_module.BLOCK_REMOVED}
        for item in drift
    )

    if from_embedded and requested_ids is None:
        # The manifest is the authority on the clone path, and only an explicit
        # snippet list overrides it. Accepting detected suggestions must not,
        # because the reader's library may be empty: that is the whole reason the
        # content travels inside the manifest. Letting --yes mean both "confirm"
        # and "use detected instead" silently composed an empty block.
        selection: tuple[Snippet, ...] = snippets_from_manifest(manifest)  # type: ignore[arg-type]
        source: SelectionSource = "embedded"
    else:
        selection, source = resolve_selection(
            library,
            manifest=manifest,
            requested_ids=requested_ids,
            detected_ids=suggested_ids,
            accept_detected=accept_detected,
            selector=selector,
        )

    recorded_mode = _recorded_mode(manifest)
    mode = resolve_mode(
        requested=requested_mode,
        recorded=recorded_mode,
        default=default_mode,
        ask=ask_mode,
    )
    import_target = _import_target(root, import_from, mode)
    composed = composition.compose(selection, mode=mode, import_target=import_target)

    return InitPlan(
        root=root,
        mode=mode,
        selection=selection,
        selection_source=source,
        detected_stack=detected_stack,
        targets=_targets(root, composed, import_from is not None),
        drift=drift,
        imports=composed.imports,
        from_embedded=from_embedded,
    )


def _detect(root: Path, library: LibraryView) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the signal files found, and the snippet ids they suggest.

    These are two different things and conflating them is a mistake worth naming:
    the found files are what the manifest records as the detected stack, while the
    suggested ids are what the picker pre-checks. A signal filename is not a
    snippet id.
    """
    signals = {signal for snippet in library.snippets for signal in snippet.stack_signals}
    found = platform.scan_stack_signals(root, signals)
    suggested = tuple(
        snippet.id
        for snippet in library.snippets
        if any(signal in found for signal in snippet.stack_signals)
    )
    return found, suggested


def _recorded_mode(manifest: manifest_module.Manifest | None) -> Mode | None:
    if manifest is None:
        return None
    entry = manifest.files.get(manifest_module.CLAUDE_MD_KEY)
    return None if entry is None else entry.mode


def _import_target(root: Path, import_from: str | None, mode: Mode) -> str:
    """Resolve what CLAUDE.md points at in import mode."""
    if import_from is None:
        return "AGENTS.md"
    if mode != composition.IMPORT:
        raise AttentionError(
            "--agents-from applies only to import mode, because copy mode "
            "materializes content instead of pointing at it"
        )
    source = Path(import_from).expanduser()
    absolute = source if source.is_absolute() else (root / source)
    if not files.path_exists(absolute):
        raise AttentionError(f"{absolute}: no AGENTS.md to import from")
    return relative_import_target(absolute, root)


def relative_import_target(agents_path: Path, claude_dir: Path) -> str:
    """The `@import` path from a CLAUDE.md to its AGENTS.md, relative and POSIX.

    Relative so the directive keeps working after the pair is moved together,
    POSIX because that is the form the directive is written in on every
    platform.
    """
    return Path(os.path.relpath(agents_path, claude_dir)).as_posix()


def _targets(
    root: Path, composed: composition.Composition, alternate_import: bool
) -> tuple[FileTarget, ...]:
    """Which files this run writes.

    An alternate import source is somebody else's file, so it is never written
    here: only this directory's CLAUDE.md is.
    """
    claude = FileTarget(
        key=manifest_module.CLAUDE_MD_KEY,
        path=root / "CLAUDE.md",
        block_id=managed_block.CLAUDE_MANAGED_BLOCK,
        content=composed.claude_block,
        relative_path="CLAUDE.md",
    )
    if alternate_import:
        return (claude,)
    return (
        FileTarget(
            key=manifest_module.AGENTS_MD_KEY,
            path=root / "AGENTS.md",
            block_id=managed_block.AGENTS_COMPOSITION_BLOCK,
            content=composed.agents_block,
            relative_path="AGENTS.md",
        ),
        claude,
    )


def apply(
    plan_to_apply: InitPlan,
    *,
    generated_by: str,
    drift_choices: Mapping[str, DriftChoice] | None = None,
    now: str | None = None,
) -> InitResult:
    """Write the managed files, then the manifest.

    The manifest is written last and only for files that actually succeeded, so
    a failure partway leaves a file mdcompose does not know it wrote. That
    surfaces as drift on the next run, which is a state the tool already
    handles, rather than as silent divergence.
    """
    choices = dict(drift_choices or {})
    if any(choice == ABORT for choice in choices.values()):
        raise AttentionError("aborted before writing anything")

    written: list[str] = []
    unchanged: list[str] = []
    kept: list[str] = []
    entries: dict[str, manifest_module.FileEntry] = {}

    for target in plan_to_apply.targets:
        if choices.get(target.key) == KEEP:
            kept.append(target.key)
            entries[target.key] = _entry_for_existing(target, plan_to_apply)
            continue
        if composition.apply_to_file(target.path, target.block_id, target.content):
            written.append(target.key)
        else:
            unchanged.append(target.key)
        entries[target.key] = _entry_for(target, plan_to_apply)

    manifest_target = manifest_module.manifest_path(plan_to_apply.root)
    manifest_module.write_manifest(
        manifest_module.build(
            generated_by=generated_by,
            generated_at=now or datetime.now(UTC).replace(microsecond=0).isoformat(),
            detected_stack=plan_to_apply.detected_stack,
            snippets=_snippet_entries(plan_to_apply.selection),
            files_recorded=entries,
            source=manifest_target,
        ),
        manifest_target,
    )
    return InitResult(
        written=tuple(written),
        unchanged=tuple(unchanged),
        kept=tuple(kept),
        manifest_path=manifest_target,
    )


def _entry_for(target: FileTarget, plan_to_apply: InitPlan) -> manifest_module.FileEntry:
    return manifest_module.FileEntry(
        path=target.relative_path,
        mode=plan_to_apply.mode,
        managed_block_hash=files.hash_content(target.content),
        imports=plan_to_apply.imports if target.key == manifest_module.CLAUDE_MD_KEY else None,
    )


def _entry_for_existing(
    target: FileTarget, plan_to_apply: InitPlan
) -> manifest_module.FileEntry:
    """Record the hash of content the user chose to keep.

    Recording what is actually there, rather than what mdcompose would have
    written, is what stops the same drift being reported on every later run. It
    also means a clone reproduces the kept version rather than the one the user
    deliberately replaced.
    """
    result = managed_block.read_blocks(target.path)
    block = result.find(target.block_id)
    content = target.content if block is None else block.content
    return manifest_module.FileEntry(
        path=target.relative_path,
        mode=plan_to_apply.mode,
        managed_block_hash=files.hash_content(content),
        imports=plan_to_apply.imports if target.key == manifest_module.CLAUDE_MD_KEY else None,
    )


def _snippet_entries(selection: Sequence[Snippet]) -> tuple[manifest_module.SnippetEntry, ...]:
    return tuple(
        manifest_module.SnippetEntry(
            id=snippet.id,
            position=index,
            applies_to=snippet.applies_to,
            content=snippet.body,
        )
        for index, snippet in enumerate(selection)
    )
