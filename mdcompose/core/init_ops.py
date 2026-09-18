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

from mdcompose.core import composition, files, managed_block, platform, skill_composition
from mdcompose.core import manifest as manifest_module
from mdcompose.core import skills as skills_module
from mdcompose.core.config import Mode
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.skills import Skill
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

#: Chooses skills, shaped exactly like ``Selector`` but over the skill library.
SkillSelector = Callable[[tuple[Skill, ...], tuple[str, ...]], tuple[str, ...]]

_EMPTY_SKILL_LIBRARY = skills_module.LibraryView(directory=Path())


@dataclass(frozen=True, slots=True)
class FileTarget:
    """One managed file: where it is, which block it owns, what goes in it.

    ``frontmatter`` is ``None`` for AGENTS.md/CLAUDE.md, where nothing sits
    outside the managed block that mdcompose itself generates. It is set for
    a skill's ``SKILL.md`` target, whose ``name``/``description`` frontmatter
    must precede the block and is regenerated on every write; see
    ``skill_composition.py``.

    ``block_id`` is ``None`` for a directory-shaped skill's accompanying file,
    which has no managed block at all: the whole file is mdcompose's, written
    and drift-checked as a unit (see ``skill_composition.apply_accompanying_file``
    and ``manifest.py``'s drift handling for an entry with no block id). Such a
    target also carries no frontmatter, which together with a ``None``
    ``block_id`` is what distinguishes it from every other target.
    """

    key: str
    path: Path
    block_id: str | None
    content: str
    relative_path: str
    frontmatter: str | None = None


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
    skill_selection: tuple[Skill, ...] = ()
    skill_selection_source: SelectionSource = "detected"
    stale_skill_paths: tuple[Path, ...] = ()

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
    deleted: tuple[str, ...] = ()
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


def resolve_skill_selection(
    library: skills_module.LibraryView,
    *,
    manifest: manifest_module.Manifest | None,
    requested_ids: tuple[str, ...] | None,
    detected_ids: tuple[str, ...],
    accept_detected: bool,
    selector: SkillSelector | None,
) -> tuple[tuple[Skill, ...], SelectionSource]:
    """Work out which skills to compose, mirroring ``resolve_selection``.

    The one divergence: an empty skill library with no explicit selection and
    no terminal to ask on resolves to an empty selection instead of raising.
    Skills are independently optional, so a project that has never touched
    the skill library must not be blocked by it; a non-empty library still
    needs an explicit answer, the same as the snippet library does.
    """
    if requested_ids is not None:
        return _skills_for(library, requested_ids), "flag"
    if accept_detected:
        return _skills_for(library, detected_ids), "detected"

    recorded = _recorded_skill_ids(manifest)
    preselected = recorded if recorded is not None else detected_ids
    if selector is None:
        if recorded is not None:
            return _skills_for(library, recorded), "manifest"
        if library.is_empty:
            return (), "detected"
        raise AttentionError(
            "no skill selection was supplied and there is no terminal to open the "
            "picker on. Pass --skills with a comma-separated list, or --yes to "
            "accept the detected suggestions."
        )
    chosen = selector(library.skills, preselected)
    return _skills_for(library, tuple(chosen)), "picker"


def _recorded_skill_ids(manifest: manifest_module.Manifest | None) -> tuple[str, ...] | None:
    if manifest is None:
        return None
    return tuple(entry.id for entry in manifest.skills_in_order())


def _skills_for(library: skills_module.LibraryView, ids: tuple[str, ...]) -> tuple[Skill, ...]:
    """Resolve ids against the skill library, naming every one that is unknown."""
    unknown = [candidate for candidate in ids if library.find(candidate) is None]
    if unknown:
        listed = ", ".join(f"'{item}'" for item in unknown)
        available = ", ".join(item.id for item in library.skills) or "none"
        raise AttentionError(
            f"no skill named {listed} in the skill library. Available: {available}"
        )
    return tuple(library.require(candidate) for candidate in ids)


def skills_from_manifest(manifest: manifest_module.Manifest) -> tuple[Skill, ...]:
    """Build a skill selection from a manifest's embedded content.

    Used on the clone path, where the local skill library may be empty or
    may not have this skill at all. A skill entry carrying embedded
    accompanying files reconstructs as a directory-shaped skill.
    """
    return tuple(
        Skill(
            id=entry.id,
            body=entry.content,
            is_bundle=bool(entry.files),
            files=dict(entry.files),
        )
        for entry in manifest.skills_in_order()
    )


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
    skill_library: skills_module.LibraryView | None = None,
    requested_skill_ids: tuple[str, ...] | None = None,
    skill_selector: SkillSelector | None = None,
) -> InitPlan:
    """Decide everything init would do, without touching a single file."""
    skill_lib = _EMPTY_SKILL_LIBRARY if skill_library is None else skill_library
    detected_stack, suggested_ids, suggested_skill_ids = _detect(root, library, skill_lib)
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

    if from_embedded and requested_skill_ids is None:
        skill_selection: tuple[Skill, ...] = skills_from_manifest(manifest)  # type: ignore[arg-type]
        skill_source: SelectionSource = "embedded"
    else:
        skill_selection, skill_source = resolve_skill_selection(
            skill_lib,
            manifest=manifest,
            requested_ids=requested_skill_ids,
            detected_ids=suggested_skill_ids,
            accept_detected=accept_detected,
            selector=skill_selector,
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
        targets=_targets(root, composed, import_from is not None, skill_selection),
        drift=drift,
        imports=composed.imports,
        from_embedded=from_embedded,
        skill_selection=skill_selection,
        skill_selection_source=skill_source,
        stale_skill_paths=_stale_skill_paths(root, manifest, skill_selection),
    )


def _detect(
    root: Path, library: LibraryView, skill_library: skills_module.LibraryView
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Return the signal files found, and the snippet and skill ids they suggest.

    One scan of the target directory feeds both pickers' pre-checks: the found
    files are what the manifest records as the detected stack, while the two
    suggested-id tuples are what each picker pre-checks. A signal filename is
    not an id in either library.
    """
    signals = {signal for snippet in library.snippets for signal in snippet.stack_signals}
    signals |= {signal for skill in skill_library.skills for signal in skill.stack_signals}
    found = platform.scan_stack_signals(root, signals)
    suggested = tuple(
        snippet.id
        for snippet in library.snippets
        if any(signal in found for signal in snippet.stack_signals)
    )
    suggested_skills = tuple(
        skill.id
        for skill in skill_library.skills
        if any(signal in found for signal in skill.stack_signals)
    )
    return found, suggested, suggested_skills


def _stale_skill_paths(
    root: Path, manifest: manifest_module.Manifest | None, selection: Sequence[Skill]
) -> tuple[Path, ...]:
    """Manifest-recorded skill files no longer part of the selection, by full path.

    Anything in ``manifest.files`` keyed by something other than the two
    well-known AGENTS.md/CLAUDE.md keys is a skill entry: either a skill's own
    id (its ``SKILL.md``), or ``<skill id>:<relative path>`` (one of its
    accompanying files; see ``manifest.py``'s schema). A file is stale when its
    owning skill is no longer selected at all, or, for an accompanying file,
    when that skill is still selected but no longer carries that particular
    file.
    """
    if manifest is None:
        return ()
    current_files = {skill.id: set(skill.files) for skill in selection}
    return tuple(
        root / entry.path
        for key, entry in manifest.files.items()
        if key not in {manifest_module.AGENTS_MD_KEY, manifest_module.CLAUDE_MD_KEY}
        and _is_stale_skill_key(key, current_files)
    )


def _is_stale_skill_key(key: str, current_files: Mapping[str, set[str]]) -> bool:
    """Whether a skill-keyed manifest entry no longer belongs to the selection."""
    skill_id, _, relative = key.partition(":")
    if skill_id not in current_files:
        return True
    return bool(relative) and relative not in current_files[skill_id]


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
    root: Path,
    composed: composition.Composition,
    alternate_import: bool,
    skill_selection: Sequence[Skill] = (),
) -> tuple[FileTarget, ...]:
    """Which files this run writes.

    An alternate import source is somebody else's file, so it is never written
    here: only this directory's CLAUDE.md is. Skill targets are independent of
    both: a project can compose skills with no AGENTS.md/CLAUDE.md change, and
    the reverse.
    """
    claude = FileTarget(
        key=manifest_module.CLAUDE_MD_KEY,
        path=root / "CLAUDE.md",
        block_id=managed_block.CLAUDE_MANAGED_BLOCK,
        content=composed.claude_block,
        relative_path="CLAUDE.md",
    )
    base = (claude,) if alternate_import else (
        FileTarget(
            key=manifest_module.AGENTS_MD_KEY,
            path=root / "AGENTS.md",
            block_id=managed_block.AGENTS_COMPOSITION_BLOCK,
            content=composed.agents_block,
            relative_path="AGENTS.md",
        ),
        claude,
    )
    return base + _skill_targets(root, skill_selection)


def _skill_targets(root: Path, selection: Sequence[Skill]) -> tuple[FileTarget, ...]:
    targets: list[FileTarget] = []
    for skill in selection:
        targets.append(
            FileTarget(
                key=skill.id,
                path=skill_composition.skill_path(root, skill.id),
                block_id=managed_block.SKILL_MANAGED_BLOCK,
                content=_skill_body(skill),
                relative_path=skill_composition.skill_path(Path(), skill.id).as_posix(),
                frontmatter=skill_composition.render_frontmatter(skill),
            )
        )
        targets.extend(_accompanying_targets(root, skill))
    return tuple(targets)


def _accompanying_targets(root: Path, skill: Skill) -> tuple[FileTarget, ...]:
    """One target per accompanying file of a directory-shaped skill.

    ``block_id`` is ``None`` and ``frontmatter`` is left at its default,
    which together mark this as neither a ``SKILL.md`` target nor an
    AGENTS.md/CLAUDE.md target: see ``FileTarget``.
    """
    skill_dir = skill_composition.skill_path(root, skill.id).parent
    relative_skill_dir = skill_composition.skill_path(Path(), skill.id).parent
    return tuple(
        FileTarget(
            key=f"{skill.id}:{relative}",
            path=skill_dir / relative,
            block_id=None,
            content=content,
            relative_path=(relative_skill_dir / relative).as_posix(),
        )
        for relative, content in sorted(skill.files.items())
    )


def _skill_body(skill: Skill) -> str:
    normalized = files.normalize(skill.body).strip("\n")
    return f"{normalized}\n" if normalized else ""


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

    deleted = _delete_stale_skill_files(plan_to_apply.stale_skill_paths)

    written: list[str] = []
    unchanged: list[str] = []
    kept: list[str] = []
    entries: dict[str, manifest_module.FileEntry] = {}

    for target in plan_to_apply.targets:
        if choices.get(target.key) == KEEP:
            kept.append(target.key)
            entries[target.key] = _entry_for_existing(target, plan_to_apply)
            continue
        if target.frontmatter is not None:
            assert target.block_id is not None  # a SKILL.md target always has one
            changed = skill_composition.apply_to_file(
                target.path, target.block_id, target.content, target.frontmatter
            )
        elif target.block_id is None:
            changed = skill_composition.apply_accompanying_file(target.path, target.content)
        else:
            changed = composition.apply_to_file(target.path, target.block_id, target.content)
        if changed:
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
            skills=_skill_entries(plan_to_apply.skill_selection),
            files_recorded=entries,
            source=manifest_target,
        ),
        manifest_target,
    )
    return InitResult(
        written=tuple(written),
        unchanged=tuple(unchanged),
        kept=tuple(kept),
        deleted=deleted,
        manifest_path=manifest_target,
    )


def _delete_stale_skill_files(paths: Sequence[Path]) -> tuple[str, ...]:
    """Delete manifest-recorded skill files no longer part of the selection.

    Removes empty directories left behind afterward, walking upward from each
    deleted file's parent. The walk stops at, and never removes, the shared
    `.claude/skills` directory itself, never a directory the user has put
    something else into, and it revisits a directory left empty by an earlier
    deletion in the same batch (a bundle skill's own directory can become
    empty only after its last accompanying file is gone).
    """
    deleted: list[str] = []
    for path in paths:
        if files.path_exists(path) and path.is_file():
            path.unlink()
            deleted.append(path.as_posix())
        _remove_empty_ancestors(path.parent)
    return tuple(deleted)


def _remove_empty_ancestors(directory: Path) -> None:
    current = directory
    while (
        files.path_exists(current)
        and current.is_dir()
        and current.name != skill_composition.SKILLS_DIR_NAME
        and not any(current.iterdir())
    ):
        parent = current.parent
        current.rmdir()
        current = parent


def _entry_mode(target: FileTarget, plan_to_apply: InitPlan) -> Mode:
    """A skill target has no import/copy distinction; it is always materialized."""
    if target.frontmatter is not None or target.block_id is None:
        return composition.COPY
    return plan_to_apply.mode


def _entry_for(target: FileTarget, plan_to_apply: InitPlan) -> manifest_module.FileEntry:
    return manifest_module.FileEntry(
        path=target.relative_path,
        mode=_entry_mode(target, plan_to_apply),
        managed_block_hash=files.hash_content(target.content),
        block_id=target.block_id,
        imports=plan_to_apply.imports if target.key == manifest_module.CLAUDE_MD_KEY else None,
    )


def _entry_for_existing(
    target: FileTarget, plan_to_apply: InitPlan
) -> manifest_module.FileEntry:
    """Record the hash of content the user chose to keep.

    Recording what is actually there, rather than what mdcompose would have
    written, is what stops the same drift being reported on every later run. It
    also means a clone reproduces the kept version rather than the one the user
    deliberately replaced. An accompanying file has no managed block to read
    the kept content from: the whole file is what was kept.
    """
    if target.block_id is None:
        content = files.read_text(target.path)
    else:
        result = managed_block.read_blocks(target.path)
        block = result.find(target.block_id)
        content = target.content if block is None else block.content
    return manifest_module.FileEntry(
        path=target.relative_path,
        mode=_entry_mode(target, plan_to_apply),
        managed_block_hash=files.hash_content(content),
        block_id=target.block_id,
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


def _skill_entries(selection: Sequence[Skill]) -> tuple[manifest_module.SkillEntry, ...]:
    return tuple(
        manifest_module.SkillEntry(
            id=skill.id, position=index, content=skill.body, files=dict(skill.files)
        )
        for index, skill in enumerate(selection)
    )
