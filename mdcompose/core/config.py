"""The global config file: schema, reading, and validation.

Two policies here look contradictory and are not. An unrecognized field is
preserved, so a config written by a newer mdcompose is not stripped by an older
one. A recognized field holding the wrong type is fatal, because silently
coercing it would produce a wrong path rather than an error.

This module only reads. Writing arrives with the config commands.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, get_args

from mdcompose.core import files
from mdcompose.core.exit_codes import AttentionError

Mode = Literal["import", "copy"]

CONFIG_FILENAME = "config.json"
SCHEMA_VERSION = 1
LIBRARY_DIR_NAME = "snippets"

#: The keys `config set` and `config unset` accept, each mapped to how its value
#: is validated. A dotted key addresses a field inside the `claude_global`
#: object. `schema_version` is deliberately absent: it describes the file format,
#: not a preference.
_PATH_KEYS = frozenset({"snippet_library_path", "global_agents_path", "claude_global.path"})
_MODE_KEYS = frozenset({"default_mode", "claude_global.mode"})
SETTABLE_KEYS: tuple[str, ...] = tuple(sorted(_PATH_KEYS | _MODE_KEYS))

_MODES: tuple[str, ...] = get_args(Mode)
_KNOWN_KEYS = frozenset(
    {
        "schema_version",
        "snippet_library_path",
        "default_mode",
        "claude_global",
        "global_agents_path",
        "registered_global_targets",
    }
)
_CLAUDE_GLOBAL_KEYS = frozenset({"path", "mode"})
_TARGET_KEYS = frozenset({"label", "path", "mode"})


@dataclass(frozen=True, slots=True)
class ClaudeGlobal:
    """The global CLAUDE.md's recorded location and mode."""

    path: str | None = None
    mode: Mode | None = None
    extra: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TargetEntry:
    """One registered tool-specific global location.

    Projection is always materialized, so the mode is always ``copy``; the field
    exists so an import-mode registration can be rejected rather than silently
    ignored.
    """

    label: str
    path: str
    mode: Mode = "copy"


@dataclass(frozen=True, slots=True)
class GlobalConfig:
    """The user's personal preferences, as read from disk.

    Every field may be unset. An absent config file is a valid state, not an
    error, and yields an instance whose ``source`` is ``None``.
    """

    schema_version: int | None = None
    snippet_library_path: str | None = None
    default_mode: Mode | None = None
    claude_global: ClaudeGlobal | None = None
    global_agents_path: str | None = None
    registered_global_targets: tuple[TargetEntry, ...] = ()
    extra: Mapping[str, object] = field(default_factory=dict)
    source: Path | None = None

    @property
    def exists(self) -> bool:
        """Whether a config file was actually present."""
        return self.source is not None

    @property
    def library_path_is_explicit(self) -> bool:
        """Whether the user chose the snippet library location themselves.

        Used to suppress the warning about a separate Windows-side library: a
        user who has already set the path does not need telling about it.
        """
        return self.snippet_library_path is not None


def config_path(config_directory: Path) -> Path:
    """Return the config file's path inside a config directory."""
    return config_directory / CONFIG_FILENAME


def load_config(path: Path) -> GlobalConfig:
    """Read the global config, treating an absent file as all fields unset.

    Never creates the file or its directory. Raises ``AttentionError`` naming
    the path and the specific problem when the file exists but cannot be used.
    """
    if not files.path_exists(path):
        return GlobalConfig()
    return load_config_text(files.read_text(path), path)


def load_config_text(text: str, path: Path) -> GlobalConfig:
    """Parse config text into a ``GlobalConfig``, raising on any problem.

    Used to read a file and to validate an edited candidate before it replaces
    the working config, so a bad edit is refused by exactly the rules a bad file
    is.
    """
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AttentionError(
            f"{path}: not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg})"
        ) from exc
    return _parse(raw, path)


def _parse(raw: object, path: Path) -> GlobalConfig:
    if not isinstance(raw, dict):
        raise AttentionError(f"{path}: top level must be a JSON object")
    return GlobalConfig(
        schema_version=_as_int(raw, "schema_version", path),
        snippet_library_path=_as_str(raw, "snippet_library_path", path),
        default_mode=_as_mode(raw, "default_mode", path),
        claude_global=_as_claude_global(raw, path),
        global_agents_path=_as_str(raw, "global_agents_path", path),
        registered_global_targets=_as_targets(raw, path),
        extra={key: value for key, value in raw.items() if key not in _KNOWN_KEYS},
        source=path,
    )


def _as_targets(raw: Mapping[str, object], path: Path) -> tuple[TargetEntry, ...]:
    """Parse and validate the registered global targets list.

    Each entry needs a label and an absolute path; labels and paths are each
    unique. These rules are why the generic config setter cannot own this field.
    """
    key = "registered_global_targets"
    if key not in raw or raw[key] is None:
        return ()
    value = raw[key]
    if not isinstance(value, list):
        raise AttentionError(f"{path}: '{key}' must be a list")

    entries: list[TargetEntry] = []
    labels: set[str] = set()
    paths: set[str] = set()
    for index, item in enumerate(value):
        entry = _one_target(item, index, path)
        if entry.label in labels:
            raise AttentionError(f"{path}: two targets share the label '{entry.label}'")
        if entry.path in paths:
            raise AttentionError(f"{path}: two targets share the path '{entry.path}'")
        labels.add(entry.label)
        paths.add(entry.path)
        entries.append(entry)
    return tuple(entries)


def _one_target(item: object, index: int, path: Path) -> TargetEntry:
    where = f"'registered_global_targets' entry {index}"
    if not isinstance(item, dict):
        raise AttentionError(f"{path}: {where} must be an object")
    label = item.get("label")
    target_path = item.get("path")
    if not isinstance(label, str) or not label:
        raise AttentionError(f"{path}: {where} needs a non-empty 'label'")
    if not isinstance(target_path, str) or not target_path:
        raise AttentionError(f"{path}: {where} needs a 'path'")
    if not (Path(target_path).is_absolute() or target_path.startswith("/")):
        raise AttentionError(f"{path}: {where} 'path' must be absolute, found '{target_path}'")
    mode = item.get("mode", "copy")
    if mode == "import":
        raise AttentionError(
            f"{path}: {where} 'mode' must be 'copy'; no other tool resolves an import directive"
        )
    if mode != "copy":
        raise AttentionError(f"{path}: {where} 'mode' must be 'copy', found '{mode}'")
    unknown = set(item) - _TARGET_KEYS
    if unknown:
        raise AttentionError(f"{path}: {where} has an unrecognized key '{sorted(unknown)[0]}'")
    return TargetEntry(label=label, path=target_path, mode=mode)  # type: ignore[arg-type]


def _as_int(raw: Mapping[str, object], key: str, path: Path) -> int | None:
    if key not in raw or raw[key] is None:
        return None
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise AttentionError(f"{path}: '{key}' must be a whole number")
    return value


def _as_str(raw: Mapping[str, object], key: str, path: Path) -> str | None:
    if key not in raw or raw[key] is None:
        return None
    value = raw[key]
    if not isinstance(value, str):
        raise AttentionError(f"{path}: '{key}' must be a string")
    return value


def _as_mode(raw: Mapping[str, object], key: str, path: Path) -> Mode | None:
    value = _as_str(raw, key, path)
    if value is None:
        return None
    if value not in _MODES:
        allowed = " or ".join(f"'{mode}'" for mode in _MODES)
        raise AttentionError(f"{path}: '{key}' must be {allowed}, found '{value}'")
    return value  # type: ignore[return-value]


def _as_claude_global(raw: Mapping[str, object], path: Path) -> ClaudeGlobal | None:
    if "claude_global" not in raw or raw["claude_global"] is None:
        return None
    value = raw["claude_global"]
    if not isinstance(value, dict):
        raise AttentionError(f"{path}: 'claude_global' must be a JSON object")
    return ClaudeGlobal(
        path=_as_str(value, "path", path),
        mode=_as_mode(value, "mode", path),
        extra={key: item for key, item in value.items() if key not in _CLAUDE_GLOBAL_KEYS},
    )


def library_dir(config: GlobalConfig, config_directory: Path) -> Path:
    """Return the snippet library directory, configured or defaulted.

    An unset ``snippet_library_path`` defaults to a ``snippets`` directory
    inside the config directory. This does not create the directory: an absent
    library is an empty library, not an error.
    """
    if config.snippet_library_path is not None:
        return Path(config.snippet_library_path).expanduser()
    return config_directory / LIBRARY_DIR_NAME


FieldState = Literal["set", "default", "not-configured", "unrecognized"]


@dataclass(frozen=True, slots=True)
class FieldView:
    """One config field as ``config show`` presents it."""

    key: str
    value: str
    state: FieldState


def describe(config: GlobalConfig, config_directory: Path) -> tuple[FieldView, ...]:
    """Every recognized field with its effective value and where that value came from."""
    views: list[FieldView] = []
    if config.snippet_library_path is not None:
        views.append(FieldView("snippet_library_path", config.snippet_library_path, "set"))
    else:
        resolved = library_dir(config, config_directory).as_posix()
        views.append(FieldView("snippet_library_path", resolved, "default"))
    views.append(_scalar_view("default_mode", config.default_mode))
    views.append(_scalar_view("global_agents_path", config.global_agents_path))
    nested = config.claude_global
    views.append(_scalar_view("claude_global.path", None if nested is None else nested.path))
    views.append(_scalar_view("claude_global.mode", None if nested is None else nested.mode))
    for target in config.registered_global_targets:
        views.append(FieldView(f"target[{target.label}]", target.path, "set"))
    for name, value in sorted(config.extra.items()):
        views.append(FieldView(name, _render_value(value), "unrecognized"))
    if nested is not None:
        for name, value in sorted(nested.extra.items()):
            views.append(FieldView(f"claude_global.{name}", _render_value(value), "unrecognized"))
    return tuple(views)


def _scalar_view(key: str, value: object) -> FieldView:
    if value is None:
        return FieldView(key, "-", "not-configured")
    return FieldView(key, str(value), "set")


def _render_value(value: object) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def is_path_key(key: str) -> bool:
    """Whether ``key`` names a path field, for the caller's boundary warning."""
    return key in _PATH_KEYS


def render(config: GlobalConfig) -> str:
    """The exact text a config write produces, also used to seed ``config edit``."""
    return json.dumps(to_document(config), indent=2, ensure_ascii=True) + "\n"


def is_set(config: GlobalConfig, key: str) -> bool:
    """Whether ``key`` carries an explicit value in the config, for unset's no-op path."""
    if key not in SETTABLE_KEYS:
        return False
    if "." not in key:
        return getattr(config, key) is not None
    _, nested_key = key.split(".", 1)
    nested = config.claude_global
    return nested is not None and getattr(nested, nested_key) is not None


def apply_set(config: GlobalConfig, key: str, raw_value: str) -> GlobalConfig:
    """Return the config with ``key`` set to a validated value.

    Validation happens here, before anything is written, so a rejected value
    cannot have touched the file. Raises ``AttentionError`` naming the field and,
    for a bad value, what was allowed.
    """
    _reject_unsettable(key)
    if key in _MODE_KEYS:
        value: object = _validated_mode_value(key, raw_value)
    else:
        value = _expanded_path(raw_value)
    return _with_key(config, key, value)


def apply_unset(config: GlobalConfig, key: str) -> GlobalConfig:
    """Return the config with ``key`` removed, so it falls back to its default."""
    _reject_unsettable(key)
    return _with_key(config, key, None)


def _reject_unsettable(key: str) -> None:
    if key == "schema_version":
        raise AttentionError(
            "'schema_version' is not user-settable: it describes the file format, "
            "not a preference"
        )
    if key == "registered_global_targets":
        raise AttentionError(
            "'registered_global_targets' is managed by the 'target' commands, not "
            "'config set'"
        )
    if key not in SETTABLE_KEYS:
        raise AttentionError(
            f"'{key}' is not a recognized config field. "
            f"Settable fields: {', '.join(SETTABLE_KEYS)}"
        )


def _validated_mode_value(key: str, raw_value: str) -> Mode:
    if raw_value not in _MODES:
        allowed = " or ".join(f"'{mode}'" for mode in _MODES)
        raise AttentionError(f"'{key}' must be {allowed}, found '{raw_value}'")
    return raw_value  # type: ignore[return-value]


def _expanded_path(raw_value: str) -> str:
    """A path value stored as an unambiguous absolute path.

    Expanded on write, not on read, so the stored value is what will actually be
    used and ``config show`` reports it verbatim, rather than one string meaning
    different things under different home directories. A leading-slash POSIX path
    is kept as-is even on Windows, where it is not "absolute" but is still what a
    WSL run will use.
    """
    expanded = Path(raw_value).expanduser()
    if expanded.is_absolute():
        return expanded.as_posix()
    if raw_value.startswith("/") or raw_value.startswith("~"):
        return expanded.as_posix()
    return (Path.cwd() / expanded).as_posix()


def _with_key(config: GlobalConfig, key: str, value: object) -> GlobalConfig:
    if "." not in key:
        return replace(config, **{key: value})
    _, nested_key = key.split(".", 1)
    current = config.claude_global or ClaudeGlobal()
    updated = replace(current, **{nested_key: value})
    if updated.path is None and updated.mode is None and not updated.extra:
        return replace(config, claude_global=None)
    return replace(config, claude_global=updated)


def to_document(config: GlobalConfig) -> dict[str, object]:
    """Render the config as the JSON document written to disk.

    Only fields that carry a value are written, and unrecognized fields are
    carried through, so a config written by a newer mdcompose is not stripped by
    an older one.
    """
    document: dict[str, object] = {"schema_version": config.schema_version or SCHEMA_VERSION}
    if config.snippet_library_path is not None:
        document["snippet_library_path"] = config.snippet_library_path
    if config.default_mode is not None:
        document["default_mode"] = config.default_mode
    if config.claude_global is not None:
        nested: dict[str, object] = {}
        if config.claude_global.path is not None:
            nested["path"] = config.claude_global.path
        if config.claude_global.mode is not None:
            nested["mode"] = config.claude_global.mode
        nested.update(config.claude_global.extra)
        document["claude_global"] = nested
    if config.global_agents_path is not None:
        document["global_agents_path"] = config.global_agents_path
    if config.registered_global_targets:
        document["registered_global_targets"] = [
            {"label": target.label, "path": target.path, "mode": target.mode}
            for target in config.registered_global_targets
        ]
    document.update(config.extra)
    return document


def write_config(config: GlobalConfig, path: Path) -> None:
    """Write the config atomically, creating its directory on first write.

    Written to a temporary file beside the target and renamed over it, so an
    interrupted write leaves the previous complete config rather than a truncated
    one. A truncated config would lose the snippet library path, which is a worse
    failure than any this tool could report.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = render(config)
    scratch = path.with_name(f"{path.name}.writing")
    try:
        files.write_text(scratch, rendered)
        scratch.replace(path)
    finally:
        if files.path_exists(scratch):
            scratch.unlink()
