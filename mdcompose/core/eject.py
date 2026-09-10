"""Stopping mdcompose from managing a directory.

`eject` is the end of the lifecycle `init` starts. It takes the managed block
markers back out of a project's files and deletes its ``mdcompose.lock``. By
default the block's content stays behind as plain markdown, so the files keep
working for whatever reads them; ``--strip`` removes the content too.

Everything outside a managed block is left exactly as it was, including anything
`import` or `convert` put there. The snippet library is never touched: ejecting
a project is not uninstalling mdcompose.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mdcompose.core import files, managed_block
from mdcompose.core import manifest as manifest_module

FileStatus = Literal["ejected", "missing", "no-block"]


@dataclass(frozen=True, slots=True)
class FileChange:
    """One managed file and what ejecting would do to it."""

    path: Path
    key: str
    status: FileStatus
    before: str
    after: str

    @property
    def modifies(self) -> bool:
        return self.status == "ejected" and not files.content_equal(self.before, self.after)


@dataclass(frozen=True, slots=True)
class EjectPlan:
    """Everything ejecting would do, worked out before a byte is written."""

    root: Path
    changes: tuple[FileChange, ...]
    manifest_to_delete: Path | None
    malformed: tuple[tuple[Path, str], ...]

    @property
    def is_empty(self) -> bool:
        ejects_a_block = any(c.status == "ejected" for c in self.changes)
        return not ejects_a_block and self.manifest_to_delete is None


def plan_eject(root: Path, *, strip: bool) -> EjectPlan:
    """Work out the eject: which files lose a block, and whether the manifest goes.

    Reachable states are all handled here rather than treated as errors: a
    drifted block (ejected as-is), a missing file (reported and skipped), a
    manifest with no markers, markers with no manifest. Only malformed markers
    are fatal, and that is decided by the caller from ``malformed``.
    """
    manifest_path = manifest_module.manifest_path(root)
    manifest = manifest_module.load_manifest(manifest_path)
    targets = _targets(root, manifest)

    changes: list[FileChange] = []
    malformed: list[tuple[Path, str]] = []
    for key, path, block_id in targets:
        if not files.path_exists(path) or not path.is_file():
            changes.append(FileChange(path, key, "missing", "", ""))
            continue
        text = files.read_text(path)
        scan = managed_block.scan(text)
        if scan.problem is not None:
            malformed.append((path, scan.problem.message))
            continue
        if scan.find(block_id) is None:
            changes.append(FileChange(path, key, "no-block", text, text))
            continue
        after = managed_block.remove(text, block_id, path, keep_content=not strip)
        changes.append(FileChange(path, key, "ejected", text, after))

    return EjectPlan(
        root=root,
        changes=tuple(changes),
        manifest_to_delete=manifest_path if files.path_exists(manifest_path) else None,
        malformed=tuple(malformed),
    )


def _targets(
    root: Path, manifest: manifest_module.Manifest | None
) -> list[tuple[str, Path, str]]:
    """The (key, path, block id) triples to eject.

    From the manifest when there is one; otherwise from whichever of the pair
    actually carries a block, so markers left behind by a hand-deleted manifest
    are still removable.
    """
    if manifest is not None:
        return [
            (key, root / entry.path, manifest_module.BLOCK_ID_BY_KEY[key])
            for key, entry in manifest.files.items()
            if key in manifest_module.BLOCK_ID_BY_KEY
        ]
    found: list[tuple[str, Path, str]] = []
    for key, name in (
        (manifest_module.AGENTS_MD_KEY, "AGENTS.md"),
        (manifest_module.CLAUDE_MD_KEY, "CLAUDE.md"),
    ):
        path = root / name
        block_id = manifest_module.BLOCK_ID_BY_KEY[key]
        if not (files.path_exists(path) and path.is_file()):
            continue
        if managed_block.scan(files.read_text(path)).find(block_id) is not None:
            found.append((key, path, block_id))
    return found


def apply_eject(plan: EjectPlan) -> tuple[str, ...]:
    """Write the modified files, then delete the manifest. Returns what changed."""
    touched: list[str] = []
    for change in plan.changes:
        if change.modifies:
            files.write_text(
                change.path, change.after, line_ending=files.line_ending_for(change.path)
            )
            touched.append(change.path.name)
    if plan.manifest_to_delete is not None:
        plan.manifest_to_delete.unlink()
        touched.append(plan.manifest_to_delete.name)
    return tuple(touched)


def render_diff(plan: EjectPlan) -> str:
    """A unified diff of every file change, plus a line naming the manifest deletion."""
    parts: list[str] = []
    for change in plan.changes:
        if change.modifies:
            parts.append(file_diff(change.path.name, change.before, change.after))
    if plan.manifest_to_delete is not None:
        parts.append(f"delete {plan.manifest_to_delete.name}")
    return "\n\n".join(part for part in parts if part)


def file_diff(name: str, before: str, after: str) -> str:
    """A unified diff between one file's current and post-eject content."""
    lines = difflib.unified_diff(
        before.splitlines(), after.splitlines(), fromfile=name, tofile=name, lineterm=""
    )
    return "\n".join(lines)


def summary(plan: EjectPlan) -> tuple[str, ...]:
    """Human-readable notes about states worth mentioning, such as a missing file."""
    notes: list[str] = []
    for change in plan.changes:
        if change.status == "missing":
            notes.append(f"{change.path.name}: recorded in the manifest but not on disk, skipped")
    return tuple(notes)


def malformed_message(plan: EjectPlan) -> str:
    """The error text for the first file whose markers cannot be parsed."""
    path, problem = plan.malformed[0]
    return f"{path}: {problem}. Fix the markers before ejecting; nothing was changed."
