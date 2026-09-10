"""Assembly of the doctor report.

The report is built here as data, so the CLI layer only has to format it and so
later changes can add a section rather than reworking the shape. Nothing in this
module writes, creates, or prompts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from mdcompose.core import config as config_module
from mdcompose.core import manifest as manifest_module
from mdcompose.core import platform as platform_module
from mdcompose.core.platform import PlatformInfo, ResolvedPath, onedrive_warning

NOT_CONFIGURED = "not configured"
PRESENT = "present"
ABSENT = "absent"


@dataclass(frozen=True, slots=True)
class PathEntry:
    """One resolved path in the report, or a note that it is not configured."""

    label: str
    resolved: ResolvedPath | None

    @property
    def status(self) -> str:
        """A one word statement of what is known about the path."""
        if self.resolved is None:
            return NOT_CONFIGURED
        return PRESENT if self.resolved.exists else ABSENT

    def to_dict(self) -> dict[str, object]:
        """Render the entry with a stable shape.

        Every key is always present, including for an entry that is not
        configured, so a consumer never has to branch on which keys exist.
        """
        return {
            "label": self.label,
            "status": self.status,
            "path": None if self.resolved is None else self.resolved.path.as_posix(),
            "on_windows_mount": (
                False if self.resolved is None else self.resolved.on_windows_mount
            ),
            "onedrive_root": None if self.resolved is None else self.resolved.onedrive_root,
        }


@dataclass(frozen=True, slots=True)
class TargetReport:
    """One registered global target and whether its file is in sync."""

    label: str
    path: str
    present: bool
    sync: str  # in-sync, out-of-sync, missing, malformed, or unknown

    @property
    def needs_attention(self) -> bool:
        return self.sync in {"out-of-sync", "missing", "malformed", "unknown"}

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "path": self.path,
            "present": self.present,
            "sync": self.sync,
        }


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Everything doctor found, ready to be formatted.

    ``drift`` is None when the target has no manifest, which means mdcompose has
    never run there. That is a state, not a fault, so it does not affect the
    exit code.
    """

    os_name: str
    is_wsl: bool
    entries: tuple[PathEntry, ...]
    warnings: tuple[str, ...]
    drift: tuple[manifest_module.FileDrift, ...] | None = None
    targets: tuple[TargetReport, ...] = ()

    @property
    def is_initialized(self) -> bool:
        return self.drift is not None

    @property
    def needs_attention(self) -> bool:
        """Whether anything reported here is the user's to resolve.

        A warning alone never counts. It reports something worth knowing rather
        than something that must be fixed.
        """
        if any(target.needs_attention for target in self.targets):
            return True
        if self.drift is None:
            return False
        return any(entry.needs_attention for entry in self.drift)

    def to_dict(self) -> dict[str, object]:
        return {
            "os": self.os_name,
            "wsl": self.is_wsl,
            "paths": [entry.to_dict() for entry in self.entries],
            "warnings": list(self.warnings),
            "initialized": self.is_initialized,
            "targets": [target.to_dict() for target in self.targets],
            "drift": None
            if self.drift is None
            else [
                {
                    "file": entry.key,
                    "path": entry.path.as_posix(),
                    "status": entry.status,
                    "detail": entry.detail,
                }
                for entry in self.drift
            ],
        }

    def to_json(self) -> str:
        """Render the report as one JSON document."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=False, ensure_ascii=True)


def build_doctor_report(
    *,
    project_root: Path,
    info: PlatformInfo | None = None,
    environ: Mapping[str, str] | None = None,
    config_directory: Path | None = None,
) -> DoctorReport:
    """Gather platform detection, path resolution, and config state.

    Raises ``AttentionError`` when the platform cannot be classified or the
    config file exists but cannot be used. Those are the two conditions that
    make doctor exit 1 in this change.

    The keyword arguments exist so tests can supply a platform, an environment,
    and a config directory instead of reaching for the real machine.
    """
    detected = platform_module.detect_platform(environ=environ) if info is None else info
    directory = platform_module.config_dir() if config_directory is None else config_directory
    configuration = config_module.load_config(config_module.config_path(directory))

    entries = _build_entries(detected, directory, configuration, project_root)
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(project_root))
    return DoctorReport(
        os_name=detected.os_name,
        is_wsl=detected.is_wsl,
        entries=entries,
        warnings=collect_warnings(
            detected,
            library_is_explicit=configuration.library_path_is_explicit,
            entries=entries,
        ),
        drift=None
        if manifest is None
        else manifest_module.detect_drift(manifest, project_root),
        targets=_build_targets(configuration, info=detected),
    )


def _build_targets(
    configuration: config_module.GlobalConfig, *, info: PlatformInfo
) -> tuple[TargetReport, ...]:
    """The sync status of every registered global target.

    ``unknown`` means the canonical global AGENTS.md is unset or not composed
    while targets are registered, which is itself a condition to resolve.
    """
    if not configuration.registered_global_targets:
        return ()
    from mdcompose.core import targets as targets_module

    canonical = _canonical_block(configuration, info)
    reports: list[TargetReport] = []
    for entry in configuration.registered_global_targets:
        path = targets_module.target_path(entry)
        sync = "unknown" if canonical is None else targets_module.sync_status(entry, canonical)
        reports.append(
            TargetReport(
                label=entry.label,
                path=path.as_posix(),
                present=platform_module.resolve_path(path, info).exists,
                sync=sync,
            )
        )
    return tuple(reports)


def _canonical_block(
    configuration: config_module.GlobalConfig, info: PlatformInfo
) -> str | None:
    from mdcompose.core import files, managed_block
    from mdcompose.core import targets as targets_module

    if configuration.global_agents_path is None:
        return None
    resolved = platform_module.resolve_path(configuration.global_agents_path, info)
    if not resolved.exists or not resolved.path.is_file():
        return None
    block = managed_block.scan(files.read_text(resolved.path)).find(targets_module.TARGET_BLOCK)
    return None if block is None else block.content


def _build_entries(
    info: PlatformInfo,
    config_directory: Path,
    configuration: config_module.GlobalConfig,
    project_root: Path,
) -> tuple[PathEntry, ...]:
    project = platform_module.resolve_project_paths(project_root, info)
    global_agents = configuration.global_agents_path
    return (
        PathEntry("config directory", platform_module.resolve_path(config_directory, info)),
        PathEntry(
            "config file",
            platform_module.resolve_path(config_module.config_path(config_directory), info),
        ),
        PathEntry(
            "snippet library",
            platform_module.resolve_path(
                config_module.library_dir(configuration, config_directory), info
            ),
        ),
        PathEntry("global CLAUDE.md", platform_module.resolve_global_claude_md(info)),
        PathEntry(
            "global AGENTS.md",
            None if global_agents is None else platform_module.resolve_path(global_agents, info),
        ),
        PathEntry("project directory", project.root),
        PathEntry("project CLAUDE.md", project.claude_md),
        PathEntry("project AGENTS.md", project.agents_md),
        PathEntry("project mdcompose.lock", project.manifest),
    )


def collect_warnings(
    info: PlatformInfo,
    *,
    library_is_explicit: bool,
    entries: tuple[PathEntry, ...],
) -> tuple[str, ...]:
    """Derive the report's warnings from what was resolved.

    Boundary warnings come from the entries themselves rather than from the
    process, because under WSL a user can run inside the Linux filesystem while
    a configured path points at a Windows drive, or the reverse. One
    process-level warning would misreport both cases.
    """
    warnings = [
        f"{entry.label} at {entry.resolved.path.as_posix()} is on a Windows drive mounted "
        f"under {platform_module.WINDOWS_MOUNT_PREFIX}, which crosses the WSL and Windows "
        "filesystem boundary"
        for entry in entries
        if entry.resolved is not None and entry.resolved.on_windows_mount
    ]
    warnings.extend(
        onedrive_warning(entry.label, entry.resolved.path, entry.resolved.onedrive_root)
        for entry in entries
        if entry.resolved is not None and entry.resolved.onedrive_root is not None
    )
    if info.is_wsl and not library_is_explicit:
        warnings.append(
            "running under WSL: a Windows-side mdcompose resolves a different snippet "
            "library than this one, so snippets saved here are not visible from Windows. "
            "Set 'snippet_library_path' in both environments to share one library."
        )
    return tuple(warnings)
