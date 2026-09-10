"""The project manifest, `mdcompose.lock`, and drift detection built on it.

The manifest is committed and shared. It records what a project composed, so a
clone reproduces the same files, and it records each managed block's hash, so
mdcompose can tell its own writes apart from a hand edit.

Two properties make a committed manifest workable. Hashes are computed over
normalized content, so the same composition hashes identically on every
platform. And nothing machine-specific is allowed in: no absolute paths, no
operating system, no hostname. Both are enforced here rather than left to
discipline.

Reading and writing both live here. Writing validates the machine-independence
rule on the way out as well as on the way in, so a bug that would record an
absolute path is caught before the file is committed rather than by whoever
clones the project.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, get_args

from mdcompose.core import files, managed_block
from mdcompose.core.config import Mode
from mdcompose.core.exit_codes import AttentionError

MANIFEST_FILENAME = "mdcompose.lock"
SCHEMA_VERSION = 1

AGENTS_MD_KEY = "agents_md"
CLAUDE_MD_KEY = "claude_md"

#: Which managed block belongs to which manifest entry. Drift detection has to
#: know this to find the block whose hash it is checking.
BLOCK_ID_BY_KEY: Mapping[str, str] = {
    AGENTS_MD_KEY: managed_block.AGENTS_COMPOSITION_BLOCK,
    CLAUDE_MD_KEY: managed_block.CLAUDE_MANAGED_BLOCK,
}

DriftStatus = Literal["clean", "drifted", "missing", "block-removed", "malformed"]

CLEAN: DriftStatus = "clean"
DRIFTED: DriftStatus = "drifted"
MISSING: DriftStatus = "missing"
BLOCK_REMOVED: DriftStatus = "block-removed"
MALFORMED: DriftStatus = "malformed"

_MODES: tuple[str, ...] = get_args(Mode)
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "generated_by",
        "generated_at",
        "detected_stack",
        "snippets",
        "files",
    }
)
_FILE_ENTRY_KEYS = frozenset({"path", "mode", "managed_block_hash", "imports"})


@dataclass(frozen=True, slots=True)
class SnippetEntry:
    """One composed snippet, with its content embedded.

    The content is embedded so that reading the manifest never requires the
    reader to have the snippet in their own library. That is what makes a fork
    by a stranger reproduce the same files.
    """

    id: str
    position: int
    applies_to: str
    content: str


@dataclass(frozen=True, slots=True)
class FileEntry:
    """What the manifest records about one managed file."""

    path: str
    mode: Mode
    managed_block_hash: str
    imports: str | None = None
    extra: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Manifest:
    """A parsed `mdcompose.lock`."""

    schema_version: int
    generated_by: str | None
    generated_at: str | None
    detected_stack: tuple[str, ...]
    snippets: tuple[SnippetEntry, ...]
    files: Mapping[str, FileEntry]
    extra: Mapping[str, object]
    source: Path

    def snippets_in_order(self) -> tuple[SnippetEntry, ...]:
        """Return the composed snippets in composition order.

        The order comes from the manifest alone, so a reader with an empty
        library still knows what goes where.
        """
        return tuple(sorted(self.snippets, key=lambda entry: entry.position))


def manifest_path(project_root: Path) -> Path:
    """Return the manifest's path inside a target directory."""
    return project_root / MANIFEST_FILENAME


def load_manifest(path: Path) -> Manifest | None:
    """Read a manifest, returning None when the project is not initialized.

    An absent manifest is a state, not an error: it means mdcompose has never
    run here. Never creates the file. Raises ``AttentionError`` naming the path
    when the file exists but cannot be used.
    """
    if not files.path_exists(path):
        return None
    text = files.read_text(path)
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AttentionError(
            f"{path}: not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg})"
        ) from exc
    return _parse(raw, path)


def _parse(raw: object, path: Path) -> Manifest:
    if not isinstance(raw, dict):
        raise AttentionError(f"{path}: top level must be a JSON object")
    version = _as_int(raw, "schema_version", path)
    if version is None:
        raise AttentionError(f"{path}: 'schema_version' is required")
    if version > SCHEMA_VERSION:
        raise AttentionError(
            f"{path}: written by a newer mdcompose (schema version {version}, "
            f"this version understands {SCHEMA_VERSION}). Upgrade mdcompose to read it."
        )
    return Manifest(
        schema_version=version,
        generated_by=_as_str(raw, "generated_by", path),
        generated_at=_as_str(raw, "generated_at", path),
        detected_stack=_as_str_list(raw, "detected_stack", path),
        snippets=_as_snippets(raw, path),
        files=_as_files(raw, path),
        extra={key: value for key, value in raw.items() if key not in _MANIFEST_KEYS},
        source=path,
    )


def _as_int(raw: Mapping[str, object], key: str, path: Path) -> int | None:
    if key not in raw or raw[key] is None:
        return None
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise AttentionError(f"{path}: '{key}' must be a whole number")
    return value


def _as_str(raw: Mapping[str, object], key: str, path: Path, *, context: str = "") -> str | None:
    if key not in raw or raw[key] is None:
        return None
    value = raw[key]
    if not isinstance(value, str):
        raise AttentionError(f"{path}: {context}'{key}' must be a string")
    return value


def _as_str_list(raw: Mapping[str, object], key: str, path: Path) -> tuple[str, ...]:
    if key not in raw or raw[key] is None:
        return ()
    value = raw[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AttentionError(f"{path}: '{key}' must be a list of strings")
    return tuple(value)


def _as_snippets(raw: Mapping[str, object], path: Path) -> tuple[SnippetEntry, ...]:
    if "snippets" not in raw or raw["snippets"] is None:
        return ()
    value = raw["snippets"]
    if not isinstance(value, list):
        raise AttentionError(f"{path}: 'snippets' must be a list")
    return tuple(_as_snippet(item, index, path) for index, item in enumerate(value))


def _as_snippet(item: object, index: int, path: Path) -> SnippetEntry:
    if not isinstance(item, dict):
        raise AttentionError(f"{path}: snippet entry {index} must be a JSON object")
    identifier = _as_str(item, "id", path, context=f"snippet entry {index}: ")
    if identifier is None:
        raise AttentionError(f"{path}: snippet entry {index} has no 'id'")
    content = _as_str(item, "content", path, context=f"snippet '{identifier}': ")
    if content is None:
        raise AttentionError(
            f"{path}: snippet '{identifier}' has no 'content'. Embedded content is what "
            "lets this manifest be used by someone without the snippet in their library."
        )
    position = _as_int(item, "position", path)
    applies_to = _as_str(item, "applies_to", path, context=f"snippet '{identifier}': ")
    return SnippetEntry(
        id=identifier,
        position=index if position is None else position,
        applies_to="both" if applies_to is None else applies_to,
        content=content,
    )


def _as_files(raw: Mapping[str, object], path: Path) -> Mapping[str, FileEntry]:
    if "files" not in raw or raw["files"] is None:
        return {}
    value = raw["files"]
    if not isinstance(value, dict):
        raise AttentionError(f"{path}: 'files' must be a JSON object")
    return {key: _as_file_entry(key, item, path) for key, item in value.items()}


def _as_file_entry(key: str, item: object, path: Path) -> FileEntry:
    if not isinstance(item, dict):
        raise AttentionError(f"{path}: file entry '{key}' must be a JSON object")
    context = f"file entry '{key}': "
    relative = _as_str(item, "path", path, context=context)
    if relative is None:
        raise AttentionError(f"{path}: file entry '{key}' has no 'path'")
    if _is_absolute(relative):
        raise AttentionError(
            f"{path}: file entry '{key}' has an absolute path '{relative}'. The manifest "
            "is committed and shared, so paths must be relative to the project."
        )
    mode = _as_str(item, "mode", path, context=context)
    if mode is None or mode not in _MODES:
        allowed = " or ".join(f"'{candidate}'" for candidate in _MODES)
        raise AttentionError(f"{path}: file entry '{key}' needs a 'mode' of {allowed}")
    block_hash = _as_str(item, "managed_block_hash", path, context=context)
    if block_hash is None:
        raise AttentionError(f"{path}: file entry '{key}' has no 'managed_block_hash'")
    return FileEntry(
        path=relative,
        mode=mode,  # type: ignore[arg-type]
        managed_block_hash=block_hash,
        imports=_as_str(item, "imports", path, context=context),
        extra={name: content for name, content in item.items() if name not in _FILE_ENTRY_KEYS},
    )


def _is_absolute(candidate: str) -> bool:
    """Return whether a recorded path would escape the project.

    Checked against both path flavours rather than the host's, because a
    manifest written on Windows is read on Linux and the other way round.
    """
    return (
        Path(candidate).is_absolute()
        or candidate.startswith(("/", "\\"))
        or (len(candidate) > 1 and candidate[1] == ":")
    )


@dataclass(frozen=True, slots=True)
class FileDrift:
    """What a managed file's state is, relative to what the manifest recorded."""

    key: str
    path: Path
    status: DriftStatus
    detail: str | None = None

    @property
    def needs_attention(self) -> bool:
        """Every status but clean is something the user has to deal with."""
        return self.status != CLEAN


def detect_drift(manifest: Manifest, project_root: Path) -> tuple[FileDrift, ...]:
    """Compare every managed file against what the manifest recorded.

    This is the one implementation of drift. A reporting command and a writing
    command both call it, so they cannot disagree about a file's state.

    Five outcomes exist rather than two, because a file recorded in the manifest
    can be gone entirely, can still exist with its block deleted, or can have
    markers that no longer parse. Collapsing those into "drifted" would send a
    recovery path in the wrong direction: restoring a deleted file is not the
    same operation as reconciling an edited block.

    Reads only. Neither the managed files nor the manifest is modified.
    """
    return tuple(
        _drift_for(key, entry, project_root) for key, entry in sorted(manifest.files.items())
    )


def _drift_for(key: str, entry: FileEntry, project_root: Path) -> FileDrift:
    path = project_root / entry.path
    if not files.path_exists(path):
        return FileDrift(key=key, path=path, status=MISSING)

    result = managed_block.read_blocks(path)
    if result.problem is not None:
        return FileDrift(key=key, path=path, status=MALFORMED, detail=result.problem.message)

    block_id = BLOCK_ID_BY_KEY.get(key)
    block = None if block_id is None else result.find(block_id)
    if block is None:
        return FileDrift(
            key=key,
            path=path,
            status=BLOCK_REMOVED,
            detail=None if block_id is None else f"no '{block_id}' block in the file",
        )

    if block.content_hash == entry.managed_block_hash:
        return FileDrift(key=key, path=path, status=CLEAN)
    return FileDrift(key=key, path=path, status=DRIFTED)


def build(
    *,
    generated_by: str,
    generated_at: str,
    detected_stack: tuple[str, ...],
    snippets: tuple[SnippetEntry, ...],
    files_recorded: Mapping[str, FileEntry],
    source: Path,
) -> Manifest:
    """Assemble a manifest ready to be written."""
    return Manifest(
        schema_version=SCHEMA_VERSION,
        generated_by=generated_by,
        generated_at=generated_at,
        detected_stack=detected_stack,
        snippets=snippets,
        files=dict(files_recorded),
        extra={},
        source=source,
    )


def to_document(manifest: Manifest) -> dict[str, object]:
    """Render a manifest as the JSON document that gets committed.

    Formatted for a person, because this file lands in pull requests. Nothing
    machine-specific goes in: no absolute paths, no operating system, no
    hostname, so the same file is correct on every machine that checks it out.
    """
    document: dict[str, object] = {
        "schema_version": manifest.schema_version,
        "generated_by": manifest.generated_by,
        "generated_at": manifest.generated_at,
        "detected_stack": list(manifest.detected_stack),
        "snippets": [
            {
                "id": entry.id,
                "position": entry.position,
                "applies_to": entry.applies_to,
                "content": entry.content,
            }
            for entry in manifest.snippets_in_order()
        ],
        "files": {
            key: _file_entry_document(entry) for key, entry in sorted(manifest.files.items())
        },
    }
    document.update(manifest.extra)
    return document


def _file_entry_document(entry: FileEntry) -> dict[str, object]:
    document: dict[str, object] = {
        "path": entry.path,
        "mode": entry.mode,
        "managed_block_hash": entry.managed_block_hash,
    }
    if entry.imports is not None:
        document["imports"] = entry.imports
    document.update(entry.extra)
    return document


def write_manifest(manifest: Manifest, path: Path) -> None:
    """Write the manifest, refusing anything machine-specific.

    Validating on the way out as well as on the way in means a bug that would
    record an absolute path is caught here rather than discovered by whoever
    clones the project.
    """
    for key, entry in manifest.files.items():
        if _is_absolute(entry.path):
            raise AttentionError(
                f"refusing to record an absolute path for '{key}': the manifest is "
                "committed and shared, so paths must be relative to the project"
            )
    rendered = json.dumps(to_document(manifest), indent=2, ensure_ascii=True) + "\n"
    files.write_text(path, rendered, line_ending=files.line_ending_for(path))
