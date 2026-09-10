"""Registered tool-specific global locations, and projecting the canonical file into them.

Claude Code reads one global file, Codex another, and other tools differ. A user
registers each location once with ``target add``; the canonical global AGENTS.md
content is then projected into a managed block inside each, whenever the global
pair is written.

The flow is one-directional. The canonical file named by ``global_agents_path``
is the only source; a target is never read as one. Projection is always
materialized content, never an import directive, because no other tool resolves
Claude Code's ``@import``. Everything outside a target's managed block is
preserved, by the same rules that protect a project's own files.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from mdcompose.core import files, managed_block
from mdcompose.core.config import GlobalConfig, TargetEntry
from mdcompose.core.exit_codes import AttentionError

TARGET_BLOCK = managed_block.AGENTS_COMPOSITION_BLOCK

SyncStatus = Literal["in-sync", "out-of-sync", "missing", "malformed"]

ProjectionStatus = Literal[
    "written", "created", "unchanged", "kept", "skipped-malformed", "skipped-unwritable"
]

DriftChoice = Literal["keep", "overwrite", "skip"]
KEEP: DriftChoice = "keep"
OVERWRITE: DriftChoice = "overwrite"
SKIP: DriftChoice = "skip"
DRIFT_CHOICES: tuple[DriftChoice, ...] = (KEEP, OVERWRITE, SKIP)


@dataclass(frozen=True, slots=True)
class ProjectionOutcome:
    label: str
    path: Path
    status: ProjectionStatus
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    outcomes: tuple[ProjectionOutcome, ...]

    @property
    def had_failure(self) -> bool:
        return any(o.status in {"skipped-malformed", "skipped-unwritable"} for o in self.outcomes)

    @property
    def wrote_anything(self) -> bool:
        return any(o.status in {"written", "created"} for o in self.outcomes)


def target_path(entry: TargetEntry) -> Path:
    return Path(entry.path).expanduser()


def add_target(
    config: GlobalConfig, label: str, raw_path: str
) -> GlobalConfig:
    """Register a target. Raises on a duplicate, a directory, or the canonical path.

    Records a preference only; nothing is written at the path.
    """
    expanded = Path(raw_path).expanduser()
    if expanded.is_absolute() or raw_path.startswith(("/", "~")):
        resolved = expanded.as_posix()
    else:
        resolved = (Path.cwd() / expanded).as_posix()

    for existing in config.registered_global_targets:
        if existing.label == label:
            raise AttentionError(f"a target labelled '{label}' is already registered")
        if _same_path(existing.path, resolved):
            raise AttentionError(
                f"'{existing.label}' is already registered at that path"
            )
    if expanded.is_dir():
        raise AttentionError(f"{resolved}: a file path is required, not a directory")
    if config.global_agents_path is not None and _same_path(config.global_agents_path, resolved):
        raise AttentionError(
            "that is the canonical global AGENTS.md; targets are projections of it, "
            "not copies of themselves"
        )
    return replace(
        config,
        registered_global_targets=(
            *config.registered_global_targets,
            TargetEntry(label=label, path=resolved, mode="copy"),
        ),
    )


def remove_target(config: GlobalConfig, label: str) -> GlobalConfig:
    """Unregister a target by label, raising when the label is unknown.

    The file at the path is left exactly where it is.
    """
    if not any(t.label == label for t in config.registered_global_targets):
        known = ", ".join(t.label for t in config.registered_global_targets) or "none"
        raise AttentionError(f"no target labelled '{label}'. Registered: {known}")
    return replace(
        config,
        registered_global_targets=tuple(
            t for t in config.registered_global_targets if t.label != label
        ),
    )


def sync_status(entry: TargetEntry, canonical_content: str) -> SyncStatus:
    """Whether a target's managed block already holds the canonical content."""
    path = target_path(entry)
    if not files.path_exists(path) or not path.is_file():
        return "missing"
    scan = managed_block.scan(files.read_text(path))
    if scan.problem is not None:
        return "malformed"
    block = scan.find(TARGET_BLOCK)
    if block is None:
        return "out-of-sync"
    return "in-sync" if files.content_equal(block.content, canonical_content) else "out-of-sync"


def project(
    config: GlobalConfig,
    canonical_content: str,
    *,
    drift_choices: dict[str, DriftChoice] | None = None,
) -> ProjectionResult:
    """Write the canonical content into every registered target's managed block.

    Failures are isolated: an unwritable path, a malformed block, or a drift the
    caller did not resolve skips that target and continues with the rest.
    """
    choices = drift_choices or {}
    outcomes: list[ProjectionOutcome] = []
    for entry in config.registered_global_targets:
        outcomes.append(_project_one(entry, canonical_content, choices.get(entry.label)))
    return ProjectionResult(outcomes=tuple(outcomes))


def _project_one(
    entry: TargetEntry, canonical_content: str, drift_choice: DriftChoice | None
) -> ProjectionOutcome:
    path = target_path(entry)
    exists = files.path_exists(path) and path.is_file()
    text = files.read_text(path) if exists else ""
    scan = managed_block.scan(text)
    if scan.problem is not None:
        return ProjectionOutcome(entry.label, path, "skipped-malformed", scan.problem.message)

    block = scan.find(TARGET_BLOCK)
    drifted = block is not None and not files.content_equal(block.content, canonical_content)
    if drifted and drift_choice != OVERWRITE:
        if drift_choice == SKIP:
            return ProjectionOutcome(entry.label, path, "kept", "skipped a drifted block")
        return ProjectionOutcome(entry.label, path, "kept", "block edited by hand, kept")

    updated = managed_block.upsert(text, TARGET_BLOCK, canonical_content, path)
    if exists and files.content_equal(text, updated):
        return ProjectionOutcome(entry.label, path, "unchanged")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        files.write_text(path, updated, line_ending=files.line_ending_for(path))
    except (OSError, AttentionError) as problem:
        return ProjectionOutcome(entry.label, path, "skipped-unwritable", str(problem))
    return ProjectionOutcome(entry.label, path, "created" if not exists else "written")


def block_diff(entry: TargetEntry, canonical_content: str) -> str:
    """A unified diff of what projecting would change in a target's block."""
    import difflib

    path = target_path(entry)
    before = None
    if path.is_file():
        before = managed_block.scan(files.read_text(path)).find(TARGET_BLOCK)
    before_text = "" if before is None else before.content
    lines = difflib.unified_diff(
        before_text.splitlines(),
        canonical_content.splitlines(),
        fromfile=entry.label,
        tofile=entry.label,
        lineterm="",
    )
    return "\n".join(lines)


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(_canon(left)) == os.path.normcase(_canon(right))


def _canon(value: str) -> str:
    candidate = Path(value).expanduser()
    try:
        return str(candidate.resolve())
    except OSError:
        return str(candidate.absolute())


def drifted_targets(
    config: GlobalConfig, canonical_content: str
) -> tuple[TargetEntry, ...]:
    """Registered targets whose managed block has been edited away from canonical."""
    return tuple(
        entry
        for entry in config.registered_global_targets
        if _has_drifted_block(entry, canonical_content)
    )


def _has_drifted_block(entry: TargetEntry, canonical_content: str) -> bool:
    path = target_path(entry)
    if not (files.path_exists(path) and path.is_file()):
        return False
    scan = managed_block.scan(files.read_text(path))
    if scan.problem is not None:
        return False
    block = scan.find(TARGET_BLOCK)
    return block is not None and not files.content_equal(block.content, canonical_content)


def import_mode_targets(entries: Sequence[TargetEntry]) -> tuple[TargetEntry, ...]:
    return tuple(entry for entry in entries if entry.mode == "import")
