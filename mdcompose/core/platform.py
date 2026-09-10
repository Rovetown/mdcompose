"""Operating system and WSL detection, and the path resolution built on them.

WSL is modelled as ``os_name == "linux"`` with ``is_wsl`` set, never as a fourth
operating system. WSL is Linux for every filesystem and path purpose, and only
differs in two places: the warning about Windows drives mounted under /mnt/, and
the fact that a Windows-side snippet library resolves to a different location.
Code that cares about POSIX semantics therefore needs no special case at all.

Nothing in this module creates a file or a directory. Resolution reports what a
path would be and whether it currently exists.
"""

from __future__ import annotations

import os
import platform as platform_module
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import platformdirs

from mdcompose.core import files
from mdcompose.core.exit_codes import AttentionError

OsName = Literal["windows", "macos", "linux"]

APP_NAME = "mdcompose"
CONFIG_DIR_ENV_VAR = "MDCOMPOSE_CONFIG_DIR"
MANIFEST_NAME = "mdcompose.lock"
CLAUDE_MD_NAME = "CLAUDE.md"
AGENTS_MD_NAME = "AGENTS.md"
GLOBAL_CLAUDE_MD = "~/.claude/CLAUDE.md"

WINDOWS_MOUNT_PREFIX = "/mnt/"

_WSL_ENV_VARS = ("WSL_DISTRO_NAME", "WSL_INTEROP", "WSLENV")
_PROC_VERSION_PATH = Path("/proc/version")
_WSL_KERNEL_MARKERS = ("microsoft", "wsl")


@dataclass(frozen=True, slots=True)
class PlatformInfo:
    """What mdcompose detected about the machine it is running on."""

    os_name: OsName
    is_wsl: bool


@dataclass(frozen=True, slots=True)
class ResolvedPath:
    """An absolute path, whether it exists, and where it sits relative to sync tools.

    ``on_windows_mount`` is per path rather than per process on purpose: under
    WSL a user can run from inside the Linux filesystem while pointing a
    configured path at a Windows drive, or the reverse, and one process-level
    flag would misreport both cases.

    ``onedrive_root`` is the OneDrive sync root this path is at or under, or
    ``None``. It is per path for the same reason, and it is a Windows-only
    signal: a synced folder there breaks Files On-Demand reads and races a
    ``mdcompose.lock`` write, but the operation is never blocked, only warned.
    """

    path: Path
    exists: bool
    on_windows_mount: bool
    onedrive_root: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """The files mdcompose manages inside one target directory."""

    root: ResolvedPath
    claude_md: ResolvedPath
    agents_md: ResolvedPath
    manifest: ResolvedPath


def detect_platform(
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    proc_version: str | None = None,
) -> PlatformInfo:
    """Detect the operating system and WSL status in one pass.

    The result is immutable and meant to be computed once per invocation and
    passed down, so no two parts of a command can disagree about the platform.

    The keyword arguments exist for tests. ``proc_version`` of ``None`` means
    read the real ``/proc/version``; pass a string, including an empty one, to
    supply its contents instead.

    Raises ``AttentionError`` if the platform cannot be classified.
    """
    detected_system = platform_module.system() if system is None else system
    os_name = _classify_os(detected_system.strip().lower())
    return PlatformInfo(
        os_name=os_name,
        is_wsl=_detect_wsl(os_name, environ=environ, proc_version=proc_version),
    )


def _classify_os(system: str) -> OsName:
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "macos"
    if system == "linux":
        return "linux"
    raise AttentionError(
        f"unsupported platform '{system}': mdcompose supports Windows, macOS, and Linux"
    )


def _detect_wsl(
    os_name: OsName,
    *,
    environ: Mapping[str, str] | None,
    proc_version: str | None,
) -> bool:
    """Return whether this is WSL, checking several independent indicators.

    Any one indicator is sufficient. Microsoft has changed both the kernel
    version string and the environment variables across WSL1 and WSL2, so
    relying on a single signal would break on some installations. A false
    negative degrades to plain Linux, which resolves correct paths and merely
    omits two warnings.

    Indicators are never consulted off Linux, so a stray environment variable
    on Windows or macOS cannot produce a WSL result.
    """
    if os_name != "linux":
        return False
    variables = os.environ if environ is None else environ
    if any(name in variables for name in _WSL_ENV_VARS):
        return True
    kernel = _read_proc_version() if proc_version is None else proc_version
    lowered = kernel.lower()
    return any(marker in lowered for marker in _WSL_KERNEL_MARKERS)


def _read_proc_version() -> str:
    """Return the kernel version string, or empty when it cannot be read."""
    if not _PROC_VERSION_PATH.is_file():
        return ""
    try:
        return _PROC_VERSION_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def config_dir(*, environ: Mapping[str, str] | None = None) -> Path:
    """Return the directory holding mdcompose's global config.

    ``MDCOMPOSE_CONFIG_DIR`` overrides the per-platform location when set to a
    non-empty value. Without it there is no way to point mdcompose at a
    different config and library, which makes it impossible to exercise the
    library commands end to end without writing into the user's real library.
    platformdirs resolves the Windows location through the known-folder API
    rather than an environment variable, so redirecting ``LOCALAPPDATA`` does
    not work and this override is the only way.

    Otherwise delegated to platformdirs, which already returns an XDG path
    inside the WSL filesystem when running under WSL. That is the desired
    answer, so WSL gets no special case here.

    This does not create the directory.
    """
    variables = os.environ if environ is None else environ
    override = variables.get(CONFIG_DIR_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    return Path(platformdirs.user_config_dir(APP_NAME, appauthor=False, roaming=False))


def resolve_path(raw: Path | str, info: PlatformInfo) -> ResolvedPath:
    """Resolve one path to absolute form and report what is known about it.

    A leading ``~`` is expanded and a relative path is anchored to the current
    working directory. The path need not exist; a missing file, and one that
    cannot be inspected at all, are both reported as absent rather than raising.

    A value that cannot be turned into a path at all is a condition the user
    must fix, so it is reported as one. Note that many odd values, a null byte
    among them, construct successfully and only fail when inspected; those are
    reported as absent, because withholding the whole report would hide the very
    entry that explains the problem.
    """
    try:
        expanded = Path(raw).expanduser()
    except (OSError, ValueError) as exc:
        raise AttentionError(f"{raw!r}: not a usable path ({exc})") from exc
    absolute = expanded if expanded.is_absolute() else Path.cwd() / expanded
    return ResolvedPath(
        path=absolute,
        exists=files.path_exists(absolute),
        on_windows_mount=is_on_windows_mount(absolute, info),
        onedrive_root=onedrive_root_for(absolute, info),
    )


def is_on_windows_mount(path: Path, info: PlatformInfo) -> bool:
    """Return whether path lies on a Windows drive mounted under /mnt/.

    Only meaningful under WSL, where that location crosses the WSL and Windows
    filesystem boundary and carries its own performance and permission quirks.
    """
    if not info.is_wsl:
        return False
    return path.as_posix().startswith(WINDOWS_MOUNT_PREFIX)


#: The three environment variables the OneDrive client sets, one per account
#: type. A machine may have any combination.
_ONEDRIVE_ENV_VARS = ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")

#: Registry path holding one subkey per configured OneDrive account, each with a
#: ``UserFolder`` value naming that account's local sync root.
_ONEDRIVE_ACCOUNTS_KEY = r"Software\Microsoft\OneDrive\Accounts"


def onedrive_roots(*, environ: Mapping[str, str] | None = None) -> tuple[Path, ...]:
    """Every OneDrive sync root configured on this machine.

    Empty off Windows. Sourced from the ``OneDrive*`` environment variables and,
    as a fallback for a shell that did not inherit them, the per-account
    ``UserFolder`` values under HKCU. Each is returned resolved and de-duplicated.
    """
    if sys.platform != "win32":
        return ()
    variables = os.environ if environ is None else environ
    found: list[Path] = []
    for name in _ONEDRIVE_ENV_VARS:
        value = variables.get(name, "").strip()
        if value:
            found.append(Path(value))
    found.extend(_onedrive_roots_from_registry())

    seen: dict[str, Path] = {}
    for candidate in found:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        seen.setdefault(os.path.normcase(str(resolved)), resolved)
    return tuple(seen.values())


def _onedrive_roots_from_registry() -> list[Path]:
    try:
        import winreg
    except ImportError:  # not Windows
        return []
    roots: list[Path] = []
    try:
        accounts = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ONEDRIVE_ACCOUNTS_KEY)
    except OSError:
        return []
    with accounts:
        for index in range(_MAX_ONEDRIVE_ACCOUNTS):
            try:
                name = winreg.EnumKey(accounts, index)
            except OSError:
                break
            try:
                with winreg.OpenKey(accounts, name) as account:
                    folder, _ = winreg.QueryValueEx(account, "UserFolder")
            except OSError:
                continue
            if isinstance(folder, str) and folder:
                roots.append(Path(folder))
    return roots


_MAX_ONEDRIVE_ACCOUNTS = 32


def onedrive_root_for(path: Path, info: PlatformInfo) -> str | None:
    """The OneDrive sync root ``path`` is at or under, or None.

    Windows only. Never blocks anything; it exists so ``doctor`` and ``init`` can
    warn that a managed file lives in a folder OneDrive syncs, where Files
    On-Demand placeholders and sync races bite.
    """
    if info.os_name != "windows":
        return None
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for root in onedrive_roots():
        if resolved == root or root in resolved.parents:
            return root.as_posix()
    return _onedrive_root_by_name(resolved)


ONEDRIVE_HELP_URL = "https://mdcompose.dev/onedrive"


def onedrive_warning(label: str, path: Path, root: str) -> str:
    """The one-line warning for a managed path inside a OneDrive-synced folder.

    Shared by ``doctor`` and ``init`` so the wording is identical. Names the
    concrete failures and ends with a link the maintainer will point at a short
    how-to-exclude video.
    """
    return (
        f"{label} at {path.as_posix()} is inside OneDrive ({root}). OneDrive can "
        "hand an AI agent an empty Files On-Demand placeholder instead of the file, "
        "race a mdcompose.lock write and leave a 'mdcompose-<HOST>.lock' conflict "
        "copy, and push paths past the 260-character limit. mdcompose still runs; "
        f"to move the folder out of sync see {ONEDRIVE_HELP_URL}"
    )


def _onedrive_root_by_name(resolved: Path) -> str | None:
    """Fallback: a path component named ``OneDrive`` or ``OneDrive - <org>``.

    Covers a shell that inherited neither the environment variables nor a
    readable registry, at the cost of a false positive on a folder a user
    happened to call OneDrive. Worth it: the whole feature is a warning.
    """
    parts = resolved.parts
    for index, part in enumerate(parts):
        if part == "OneDrive" or part.startswith("OneDrive - "):
            return Path(*parts[: index + 1]).as_posix()
    return None


def resolve_project_paths(root: Path | str, info: PlatformInfo) -> ProjectPaths:
    """Resolve the managed files for one target directory.

    Each target directory is independent and holds its own manifest. A parent
    directory's manifest is never consulted from here.
    """
    resolved_root = resolve_path(root, info)
    return ProjectPaths(
        root=resolved_root,
        claude_md=resolve_path(resolved_root.path / CLAUDE_MD_NAME, info),
        agents_md=resolve_path(resolved_root.path / AGENTS_MD_NAME, info),
        manifest=resolve_path(resolved_root.path / MANIFEST_NAME, info),
    )


def resolve_global_claude_md(info: PlatformInfo) -> ResolvedPath:
    """Resolve the global CLAUDE.md, whose location is fixed by Claude Code."""
    return resolve_path(GLOBAL_CLAUDE_MD, info)


def scan_stack_signals(directory: Path, signals: Iterable[str]) -> tuple[str, ...]:
    """Return which of the named signal files exist in a directory.

    Presence only. Nothing is parsed, executed, or analyzed, and no file is
    opened. The moment mdcompose read `package.json` to work out a framework it
    would inherit every version of that format, and repo-scanning generators
    already cover that ground well. A pre-check the user then corrects in the
    picker costs one keystroke when it guesses wrong.
    """
    return tuple(
        name
        for name in sorted(set(signals))
        if files.path_exists(directory / name) and (directory / name).is_file()
    )
