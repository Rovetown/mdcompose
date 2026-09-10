"""Assembly of the doctor report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mdcompose.core import config as config_module
from mdcompose.core import report as report_module
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.platform import PlatformInfo, ResolvedPath

EXPECTED_LABELS = (
    "config directory",
    "config file",
    "snippet library",
    "global CLAUDE.md",
    "global AGENTS.md",
    "project directory",
    "project CLAUDE.md",
    "project AGENTS.md",
    "project mdcompose.lock",
)


def build(
    *,
    project_root: Path,
    info: PlatformInfo,
    config_directory: Path,
) -> report_module.DoctorReport:
    return report_module.build_doctor_report(
        project_root=project_root,
        info=info,
        environ={},
        config_directory=config_directory,
    )


def test_report_covers_every_path(tmp_path: Path, windows: PlatformInfo) -> None:
    report = build(project_root=tmp_path, info=windows, config_directory=tmp_path / "config")
    assert tuple(entry.label for entry in report.entries) == EXPECTED_LABELS


def test_report_names_the_platform(tmp_path: Path, wsl: PlatformInfo) -> None:
    report = build(project_root=tmp_path, info=wsl, config_directory=tmp_path / "config")
    assert report.os_name == "linux"
    assert report.is_wsl is True


def test_unconfigured_global_agents_md_is_not_an_error(
    tmp_path: Path, windows: PlatformInfo
) -> None:
    report = build(project_root=tmp_path, info=windows, config_directory=tmp_path / "config")
    entry = next(item for item in report.entries if item.label == "global AGENTS.md")
    assert entry.resolved is None
    assert entry.status == report_module.NOT_CONFIGURED


def test_configured_global_agents_md_is_resolved(
    tmp_path: Path, windows: PlatformInfo
) -> None:
    directory = tmp_path / "config"
    directory.mkdir()
    config_module.config_path(directory).write_text(
        '{"global_agents_path": "~/.codex/AGENTS.md"}', encoding="utf-8"
    )
    report = build(project_root=tmp_path, info=windows, config_directory=directory)
    entry = next(item for item in report.entries if item.label == "global AGENTS.md")
    assert entry.resolved is not None
    assert entry.resolved.path.parent.name == ".codex"


def test_presence_is_reported_per_path(tmp_path: Path, windows: PlatformInfo) -> None:
    (tmp_path / "AGENTS.md").write_text("# here\n", encoding="utf-8")
    report = build(project_root=tmp_path, info=windows, config_directory=tmp_path / "config")
    statuses = {entry.label: entry.status for entry in report.entries}
    assert statuses["project AGENTS.md"] == report_module.PRESENT
    assert statuses["project CLAUDE.md"] == report_module.ABSENT


def test_building_the_report_creates_nothing(tmp_path: Path, windows: PlatformInfo) -> None:
    project = tmp_path / "project"
    project.mkdir()
    build(project_root=project, info=windows, config_directory=tmp_path / "config")
    assert list(project.iterdir()) == []
    assert not (tmp_path / "config").exists()


def test_no_warnings_on_a_plain_machine(tmp_path: Path, windows: PlatformInfo) -> None:
    report = build(project_root=tmp_path, info=windows, config_directory=tmp_path / "config")
    assert report.warnings == ()


def test_wsl_warns_that_the_windows_library_is_separate(
    tmp_path: Path, wsl: PlatformInfo
) -> None:
    report = build(project_root=tmp_path, info=wsl, config_directory=tmp_path / "config")
    joined = " ".join(report.warnings)
    assert "WSL" in joined
    assert "snippet_library_path" in joined


def test_the_separate_library_warning_stops_once_the_path_is_chosen(
    tmp_path: Path, wsl: PlatformInfo
) -> None:
    directory = tmp_path / "config"
    directory.mkdir()
    config_module.config_path(directory).write_text(
        '{"snippet_library_path": "/home/someone/snippets"}', encoding="utf-8"
    )
    report = build(project_root=tmp_path, info=wsl, config_directory=directory)
    assert not any("snippet_library_path" in warning for warning in report.warnings)


def test_no_separate_library_warning_outside_wsl(
    tmp_path: Path, linux: PlatformInfo
) -> None:
    report = build(project_root=tmp_path, info=linux, config_directory=tmp_path / "config")
    assert not any("snippet_library_path" in warning for warning in report.warnings)


def mounted_entry(label: str) -> report_module.PathEntry:
    """An entry already flagged as living on a Windows drive under /mnt/.

    Built directly rather than resolved, because path resolution cannot produce
    a /mnt/ path on a Windows host, and whether the flag is computed correctly
    is covered in the platform tests. Task 9.3 verifies the end to end path on
    a real WSL machine.
    """
    return report_module.PathEntry(
        label=label,
        resolved=ResolvedPath(
            path=Path("/mnt/c/Users/someone/project"),
            exists=True,
            on_windows_mount=True,
        ),
    )


def test_windows_mount_warning_names_the_boundary(wsl: PlatformInfo) -> None:
    warnings = report_module.collect_warnings(
        wsl,
        library_is_explicit=True,
        entries=(mounted_entry("project directory"),),
    )
    joined = " ".join(warnings)
    assert "/mnt/" in joined
    assert "project directory" in joined


def test_each_mounted_path_warns_separately(wsl: PlatformInfo) -> None:
    """A warning per path, since one path can cross the boundary while another does not."""
    warnings = report_module.collect_warnings(
        wsl,
        library_is_explicit=True,
        entries=(
            mounted_entry("project directory"),
            mounted_entry("snippet library"),
            report_module.PathEntry(
                label="global CLAUDE.md",
                resolved=ResolvedPath(
                    path=Path("/home/someone/.claude/CLAUDE.md"),
                    exists=False,
                    on_windows_mount=False,
                ),
            ),
        ),
    )
    assert len(warnings) == 2
    assert not any("global CLAUDE.md" in warning for warning in warnings)


def test_unconfigured_entries_never_warn(wsl: PlatformInfo) -> None:
    warnings = report_module.collect_warnings(
        wsl,
        library_is_explicit=True,
        entries=(report_module.PathEntry(label="global AGENTS.md", resolved=None),),
    )
    assert warnings == ()


def test_boundary_warnings_are_ascii(wsl: PlatformInfo) -> None:
    warnings = report_module.collect_warnings(
        wsl,
        library_is_explicit=False,
        entries=(mounted_entry("project directory"),),
    )
    assert all(warning.isascii() for warning in warnings)


def test_malformed_config_stops_the_report(tmp_path: Path, windows: PlatformInfo) -> None:
    directory = tmp_path / "config"
    directory.mkdir()
    config_module.config_path(directory).write_text("{ broken", encoding="utf-8")
    with pytest.raises(AttentionError):
        build(project_root=tmp_path, info=windows, config_directory=directory)


def test_json_document_carries_every_field(tmp_path: Path, wsl: PlatformInfo) -> None:
    report = build(project_root=tmp_path, info=wsl, config_directory=tmp_path / "config")
    payload = json.loads(report.to_json())
    assert payload["os"] == "linux"
    assert payload["wsl"] is True
    assert [entry["label"] for entry in payload["paths"]] == list(EXPECTED_LABELS)
    assert payload["warnings"] == list(report.warnings)


def test_json_document_is_ascii_only(tmp_path: Path, wsl: PlatformInfo) -> None:
    report = build(project_root=tmp_path, info=wsl, config_directory=tmp_path / "config")
    assert report.to_json().isascii()
