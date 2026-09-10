"""Platform detection and path resolution."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from mdcompose.core import platform as platform_module
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.platform import PlatformInfo

WSL1_KERNEL = "Linux version 4.4.0-19041-Microsoft (Microsoft@Microsoft.com)"
WSL2_KERNEL = "Linux version 5.15.90.1-microsoft-standard-WSL2 (oe-user@oe-host)"
NATIVE_KERNEL = "Linux version 6.8.0-45-generic (buildd@lcy02-amd64-091)"


@pytest.mark.parametrize(
    ("system", "expected"),
    [("Windows", "windows"), ("Darwin", "macos"), ("Linux", "linux"), ("linux", "linux")],
)
def test_classifies_supported_operating_systems(system: str, expected: str) -> None:
    detected = platform_module.detect_platform(system=system, environ={}, proc_version="")
    assert detected.os_name == expected


def test_unsupported_platform_is_reported_not_guessed() -> None:
    with pytest.raises(AttentionError) as raised:
        platform_module.detect_platform(system="Haiku", environ={}, proc_version="")
    assert "haiku" in str(raised.value).lower()


def test_detection_result_is_immutable() -> None:
    detected = platform_module.detect_platform(system="Linux", environ={}, proc_version="")
    with pytest.raises(dataclasses.FrozenInstanceError):
        detected.is_wsl = True  # type: ignore[misc]


@pytest.mark.parametrize(
    ("environ", "kernel"),
    [
        ({"WSL_DISTRO_NAME": "Ubuntu"}, NATIVE_KERNEL),
        ({"WSL_INTEROP": "/run/WSL/8_interop"}, NATIVE_KERNEL),
        ({}, WSL1_KERNEL),
        ({}, WSL2_KERNEL),
    ],
)
def test_any_single_indicator_is_enough_for_wsl(environ: dict[str, str], kernel: str) -> None:
    detected = platform_module.detect_platform(
        system="Linux", environ=environ, proc_version=kernel
    )
    assert detected.os_name == "linux"
    assert detected.is_wsl is True


def test_native_linux_is_not_wsl() -> None:
    detected = platform_module.detect_platform(
        system="Linux", environ={}, proc_version=NATIVE_KERNEL
    )
    assert detected.is_wsl is False


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
def test_wsl_indicators_are_ignored_off_linux(system: str) -> None:
    detected = platform_module.detect_platform(
        system=system,
        environ={"WSL_DISTRO_NAME": "Ubuntu", "WSLENV": "PATH/l"},
        proc_version=WSL2_KERNEL,
    )
    assert detected.is_wsl is False


def test_config_directory_is_absolute_and_named_for_the_tool() -> None:
    directory = platform_module.config_dir()
    assert directory.is_absolute()
    assert directory.name == platform_module.APP_NAME


def test_config_directory_resolution_is_pure(tmp_path: Path) -> None:
    """Resolving is a pure computation, so it neither creates nor varies."""
    first = platform_module.config_dir()
    second = platform_module.config_dir()
    assert first == second
    assert not (tmp_path / first.name).exists()


def test_unreadable_paths_are_reported_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, linux: PlatformInfo
) -> None:
    """A path that cannot be inspected is absent, not a crash.

    Path.exists re-raises PermissionError on Python 3.11 and 3.12 but swallows
    it on 3.13 and later, so mdcompose decides for itself and behaves the same
    on every supported version.
    """

    def deny(_self: Path) -> bool:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "exists", deny)
    assert platform_module.resolve_path(tmp_path / "denied.md", linux).exists is False


def test_an_unusable_path_value_is_reported_rather_than_crashing(
    linux: PlatformInfo,
) -> None:
    """A nonsensical path value still produces a report entry.

    doctor exists to tell the user what mdcompose sees. A path it cannot
    inspect, for whatever reason, is absent. Refusing to run because one
    configured value is malformed would withhold the report that explains it.
    """
    resolved = platform_module.resolve_path("bad" + chr(0) + "path.md", linux)
    assert resolved.exists is False


def test_resolve_expands_home_and_reports_absence(windows: PlatformInfo) -> None:
    resolved = platform_module.resolve_path("~/definitely-not-here.md", windows)
    assert resolved.path.is_absolute()
    assert "~" not in resolved.path.as_posix()
    assert resolved.exists is False


def test_resolve_anchors_a_relative_path_to_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, linux: PlatformInfo
) -> None:
    monkeypatch.chdir(tmp_path)
    resolved = platform_module.resolve_path("AGENTS.md", linux)
    assert resolved.path == tmp_path / "AGENTS.md"


def test_resolve_reports_presence(tmp_path: Path, linux: PlatformInfo) -> None:
    present = tmp_path / "here.md"
    present.write_text("x", encoding="utf-8")
    assert platform_module.resolve_path(present, linux).exists is True
    assert platform_module.resolve_path(tmp_path / "gone.md", linux).exists is False


def test_resolution_creates_nothing(tmp_path: Path, linux: PlatformInfo) -> None:
    platform_module.resolve_project_paths(tmp_path / "unborn", linux)
    assert list(tmp_path.iterdir()) == []


def test_windows_mount_flag_only_trips_under_wsl(
    wsl: PlatformInfo, linux: PlatformInfo
) -> None:
    mounted = Path("/mnt/c/Users/someone/project")
    assert platform_module.is_on_windows_mount(mounted, wsl) is True
    assert platform_module.is_on_windows_mount(mounted, linux) is False


def test_windows_mount_flag_is_false_inside_the_wsl_filesystem(wsl: PlatformInfo) -> None:
    assert platform_module.is_on_windows_mount(Path("/home/someone/project"), wsl) is False


def test_project_paths_name_the_expected_files(
    tmp_path: Path, linux: PlatformInfo
) -> None:
    paths = platform_module.resolve_project_paths(tmp_path, linux)
    assert paths.claude_md.path.name == "CLAUDE.md"
    assert paths.agents_md.path.name == "AGENTS.md"
    assert paths.manifest.path.name == "mdcompose.lock"
    assert paths.manifest.path.parent == paths.root.path


def test_global_claude_md_is_the_location_claude_code_uses(windows: PlatformInfo) -> None:
    resolved = platform_module.resolve_global_claude_md(windows)
    assert resolved.path.name == "CLAUDE.md"
    assert resolved.path.parent.name == ".claude"


def test_the_config_directory_can_be_redirected(tmp_path: Path) -> None:
    """Without this there is no way to exercise the library commands without
    writing into the real library. On Windows platformdirs resolves the location
    through the known-folder API, so redirecting LOCALAPPDATA does not work and
    this override is the only mechanism.
    """
    override = tmp_path / "elsewhere"
    resolved = platform_module.config_dir(
        environ={platform_module.CONFIG_DIR_ENV_VAR: str(override)}
    )
    assert resolved == override


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_an_empty_override_falls_back_to_the_platform_location(value: str) -> None:
    resolved = platform_module.config_dir(environ={platform_module.CONFIG_DIR_ENV_VAR: value})
    assert resolved == platform_module.config_dir(environ={})


def test_an_absent_override_falls_back_to_the_platform_location() -> None:
    assert platform_module.config_dir(environ={}).name == platform_module.APP_NAME


def test_the_override_expands_a_home_marker() -> None:
    resolved = platform_module.config_dir(
        environ={platform_module.CONFIG_DIR_ENV_VAR: "~/mdcompose-elsewhere"}
    )
    assert resolved.is_absolute()
    assert "~" not in resolved.as_posix()


def test_the_override_creates_nothing(tmp_path: Path) -> None:
    override = tmp_path / "never-created"
    platform_module.config_dir(environ={platform_module.CONFIG_DIR_ENV_VAR: str(override)})
    assert not override.exists()
