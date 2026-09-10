"""OneDrive-synced folder detection and the warning it drives on doctor and init."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import Invocation

from mdcompose.core import platform as platform_module
from mdcompose.core.exit_codes import EXIT_OK
from mdcompose.core.platform import PlatformInfo

Invoke = Callable[..., Invocation]

WINDOWS = PlatformInfo(os_name="windows", is_wsl=False)
LINUX = PlatformInfo(os_name="linux", is_wsl=False)

on_windows = pytest.mark.skipif(
    sys.platform != "win32", reason="OneDrive detection is Windows only"
)


@pytest.fixture(autouse=True)
def no_ambient_onedrive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Detach from the real machine's OneDrive so tests are deterministic."""
    for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(platform_module, "_onedrive_roots_from_registry", list)


def test_no_onedrive_configured_means_no_root(tmp_path: Path) -> None:
    assert platform_module.onedrive_roots() == ()
    assert platform_module.onedrive_root_for(tmp_path / "x", WINDOWS) is None


def test_detection_is_a_no_op_off_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OneDrive", str(tmp_path))
    assert platform_module.onedrive_root_for(tmp_path / "sub" / "file", LINUX) is None


@on_windows
def test_a_path_under_the_onedrive_env_var_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "OneDrive"
    (root / "proj").mkdir(parents=True)
    monkeypatch.setenv("OneDrive", str(root))
    detected = platform_module.onedrive_root_for(root / "proj" / "AGENTS.md", WINDOWS)
    assert detected == root.resolve().as_posix()


@on_windows
def test_a_path_outside_onedrive_is_not_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OneDrive", str(tmp_path / "OneDrive"))
    (tmp_path / "OneDrive").mkdir()
    assert platform_module.onedrive_root_for(tmp_path / "elsewhere" / "x", WINDOWS) is None


@on_windows
def test_the_name_heuristic_catches_a_business_onedrive_folder(tmp_path: Path) -> None:
    resolved = tmp_path / "OneDrive - Contoso" / "Documents" / "proj"
    detected = platform_module._onedrive_root_by_name(resolved)
    assert detected == (tmp_path / "OneDrive - Contoso").as_posix()


def test_the_warning_names_the_path_the_root_and_the_link() -> None:
    text = platform_module.onedrive_warning(
        "config directory", Path("/x/OneDrive/cfg"), "/x/OneDrive"
    )
    assert "config directory" in text
    assert "/x/OneDrive/cfg" in text and "/x/OneDrive" in text
    assert platform_module.ONEDRIVE_HELP_URL in text
    assert "still runs" in text  # never blocks


# --- doctor + init integration ---


@pytest.fixture
def onedrive_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    root = tmp_path / "OneDrive"
    config = root / "AppData" / "mdcompose"
    (config / "snippets").mkdir(parents=True)
    (config / "snippets" / "s.md").write_text("---\ntitle: s\n---\n\nbody\n", encoding="utf-8")
    monkeypatch.setenv("OneDrive", str(root))
    monkeypatch.setattr(platform_module, "config_dir", lambda: config)
    project = root / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return root


@on_windows
def test_doctor_warns_about_a_synced_config_directory_and_still_exits_zero(
    invoke: Invoke, onedrive_home: Path
) -> None:
    result = invoke("doctor")
    assert result.code == EXIT_OK
    assert "inside OneDrive" in result.err
    assert platform_module.ONEDRIVE_HELP_URL in result.err


@on_windows
def test_doctor_json_carries_the_onedrive_root(invoke: Invoke, onedrive_home: Path) -> None:
    payload = json.loads(invoke("doctor", "--json").out)
    roots = {entry["onedrive_root"] for entry in payload["paths"]}
    assert onedrive_home.resolve().as_posix() in roots


@on_windows
def test_init_warns_before_writing_into_a_synced_folder(
    invoke: Invoke, onedrive_home: Path
) -> None:
    result = invoke("init", "--mode", "copy", "--snippets", "s")
    assert result.code == EXIT_OK
    assert "inside OneDrive" in result.err
    assert "target directory" in result.err


def test_doctor_json_shape_still_has_onedrive_root_key_off_onedrive(
    invoke: Invoke, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform_module, "config_dir", lambda: tmp_path / "cfg")
    monkeypatch.chdir(tmp_path)
    payload = json.loads(invoke("doctor", "--json").out)
    assert all("onedrive_root" in entry for entry in payload["paths"])
    assert all(entry["onedrive_root"] is None for entry in payload["paths"])
