"""The config command group: show, set, unset, edit."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import Invocation

from mdcompose.core import config as config_module
from mdcompose.core import platform as platform_module
from mdcompose.core.exit_codes import EXIT_ATTENTION, EXIT_OK
from mdcompose.core.platform import PlatformInfo

Invoke = Callable[..., Invocation]


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "config"
    monkeypatch.setattr(platform_module, "config_dir", lambda: directory)
    monkeypatch.chdir(tmp_path)
    return directory


def config_file(config_dir: Path) -> Path:
    return config_dir / "config.json"


def write_raw(config_dir: Path, payload: dict) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file(config_dir).write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))


# --- section 5: config show ---


def test_show_lists_every_recognized_field(invoke: Invoke, config_dir: Path) -> None:
    result = invoke("config", "show")
    assert result.code == EXIT_OK
    for field in (
        "snippet_library_path",
        "default_mode",
        "global_agents_path",
        "claude_global.path",
        "claude_global.mode",
    ):
        assert field in result.out


def test_show_marks_a_set_value(invoke: Invoke, config_dir: Path) -> None:
    write_raw(config_dir, {"schema_version": 1, "default_mode": "copy"})
    line = next(ln for ln in invoke("config", "show").out.splitlines() if "default_mode" in ln)
    assert "copy" in line and "set" in line


def test_show_marks_a_defaulted_value(invoke: Invoke, config_dir: Path) -> None:
    line = next(
        ln for ln in invoke("config", "show").out.splitlines() if "snippet_library_path" in ln
    )
    assert "default" in line


def test_show_marks_an_unset_value_with_no_default(invoke: Invoke, config_dir: Path) -> None:
    line = next(
        ln for ln in invoke("config", "show").out.splitlines() if "global_agents_path" in ln
    )
    assert "not-configured" in line


def test_show_prints_the_config_file_path(invoke: Invoke, config_dir: Path) -> None:
    assert config_file(config_dir).as_posix() in invoke("config", "show").out


def test_show_marks_an_unrecognized_field(invoke: Invoke, config_dir: Path) -> None:
    write_raw(config_dir, {"schema_version": 1, "future_flag": "x"})
    line = next(ln for ln in invoke("config", "show").out.splitlines() if "future_flag" in ln)
    assert "unrecognized" in line


def test_show_marks_an_explicitly_set_library_path(invoke: Invoke, config_dir: Path) -> None:
    write_raw(config_dir, {"schema_version": 1, "snippet_library_path": "/somewhere/snips"})
    line = next(
        ln for ln in invoke("config", "show").out.splitlines() if "snippet_library_path" in ln
    )
    assert "set" in line and "/somewhere/snips" in line


def test_show_marks_an_unrecognized_nested_claude_global_key(
    invoke: Invoke, config_dir: Path
) -> None:
    write_raw(
        config_dir,
        {"schema_version": 1, "claude_global": {"path": "/x/CLAUDE.md", "future": "y"}},
    )
    line = next(
        ln for ln in invoke("config", "show").out.splitlines() if "claude_global.future" in ln
    )
    assert "unrecognized" in line


def test_show_with_no_config_prints_defaults_and_creates_nothing(
    invoke: Invoke, config_dir: Path
) -> None:
    result = invoke("config", "show")
    assert result.code == EXIT_OK
    assert "absent" in result.out
    assert not config_dir.exists()  # 4.3: a read creates nothing


# --- section 6: config set and unset ---


def test_set_a_top_level_field(invoke: Invoke, config_dir: Path) -> None:
    result = invoke("config", "set", "default_mode", "copy")
    assert result.code == EXIT_OK
    assert json.loads(config_file(config_dir).read_text(encoding="utf-8"))["default_mode"] == "copy"


def test_set_a_nested_field(invoke: Invoke, config_dir: Path) -> None:
    invoke("config", "set", "claude_global.mode", "import")
    document = json.loads(config_file(config_dir).read_text(encoding="utf-8"))
    assert document["claude_global"]["mode"] == "import"


def test_set_a_nested_path_writes_no_mode_key(invoke: Invoke, config_dir: Path) -> None:
    invoke("config", "set", "claude_global.path", "/x/CLAUDE.md")
    nested = json.loads(config_file(config_dir).read_text(encoding="utf-8"))["claude_global"]
    assert nested["path"] == "/x/CLAUDE.md"
    assert "mode" not in nested


def test_set_creates_the_file_and_directory(invoke: Invoke, config_dir: Path) -> None:
    assert not config_dir.exists()
    invoke("config", "set", "default_mode", "copy")
    assert config_file(config_dir).is_file()


def test_set_a_library_path_that_does_not_exist_creates_no_directory(
    invoke: Invoke, config_dir: Path
) -> None:
    target = config_dir.parent / "nowhere" / "snippets"
    invoke("config", "set", "snippet_library_path", str(target))
    assert not target.exists()
    stored = json.loads(config_file(config_dir).read_text(encoding="utf-8"))["snippet_library_path"]
    assert stored == target.as_posix()


def test_set_a_path_under_a_windows_mount_warns_and_records(
    invoke: Invoke, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        platform_module, "detect_platform", lambda: PlatformInfo(os_name="linux", is_wsl=True)
    )
    invoke("config", "set", "snippet_library_path", "/mnt/c/Users/x/snippets")
    result = invoke("config", "set", "global_agents_path", "/mnt/c/Users/x/AGENTS.md")
    assert result.code == EXIT_OK
    assert "/mnt/" in result.err
    document = json.loads(config_file(config_dir).read_text(encoding="utf-8"))
    assert document["global_agents_path"] == "/mnt/c/Users/x/AGENTS.md"


def test_unset_a_defaulted_field_falls_back_to_the_default(
    invoke: Invoke, config_dir: Path
) -> None:
    write_raw(config_dir, {"schema_version": 1, "snippet_library_path": "/x/snips"})
    invoke("config", "unset", "snippet_library_path")
    assert "snippet_library_path" not in config_file(config_dir).read_text(encoding="utf-8")
    line = next(
        ln for ln in invoke("config", "show").out.splitlines() if "snippet_library_path" in ln
    )
    assert "default" in line


def test_unset_a_field_with_no_default_reports_not_configured(
    invoke: Invoke, config_dir: Path
) -> None:
    write_raw(config_dir, {"schema_version": 1, "global_agents_path": "/x/AGENTS.md"})
    invoke("config", "unset", "global_agents_path")
    line = next(
        ln for ln in invoke("config", "show").out.splitlines() if "global_agents_path" in ln
    )
    assert "not-configured" in line


def test_unset_an_already_absent_field_is_a_no_op(invoke: Invoke, config_dir: Path) -> None:
    write_raw(config_dir, {"schema_version": 1, "default_mode": "copy"})
    before = config_file(config_dir).read_bytes()
    result = invoke("config", "unset", "global_agents_path")
    assert result.code == EXIT_OK
    assert config_file(config_dir).read_bytes() == before


def test_unset_an_already_absent_nested_field_is_a_no_op(
    invoke: Invoke, config_dir: Path
) -> None:
    write_raw(config_dir, {"schema_version": 1, "claude_global": {"path": "/x/CLAUDE.md"}})
    before = config_file(config_dir).read_bytes()
    result = invoke("config", "unset", "claude_global.mode")
    assert result.code == EXIT_OK
    assert config_file(config_dir).read_bytes() == before


def test_unset_an_unknown_key_is_refused(invoke: Invoke, config_dir: Path) -> None:
    result = invoke("config", "unset", "made_up")
    assert result.code == EXIT_ATTENTION
    assert "made_up" in result.err


# --- section 1.6: a rejected set never touches the file ---


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("default_mode", "sideways"),
        ("made_up_key", "x"),
        ("schema_version", "2"),
    ],
)
def test_a_rejected_set_leaves_the_file_byte_identical(
    invoke: Invoke, config_dir: Path, key: str, value: str
) -> None:
    write_raw(config_dir, {"schema_version": 1, "default_mode": "import"})
    before = config_file(config_dir).read_bytes()
    result = invoke("config", "set", key, value)
    assert result.code == EXIT_ATTENTION
    assert config_file(config_dir).read_bytes() == before


# --- section 7: config edit ---


def stub_editor(monkeypatch: pytest.MonkeyPatch, new_content: str | None) -> None:
    """Make the configured editor replace the file with new_content, or leave it."""

    def fake_run(argv: list[str], **_kw: object) -> object:
        path = Path(argv[-1])
        if new_content is not None:
            path.write_text(new_content, encoding="utf-8", newline="")

        class Done:
            returncode = 0

        return Done()

    monkeypatch.setenv("EDITOR", "stub-editor")
    monkeypatch.setattr("subprocess.run", fake_run)


def test_edit_installs_a_valid_result(
    invoke: Invoke, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_raw(config_dir, {"schema_version": 1, "default_mode": "import"})
    stub_editor(monkeypatch, '{"schema_version": 1, "default_mode": "copy"}\n')
    result = invoke("config", "edit")
    assert result.code == EXIT_OK
    assert json.loads(config_file(config_dir).read_text(encoding="utf-8"))["default_mode"] == "copy"


def test_edit_rejects_invalid_json_and_keeps_the_original(
    invoke: Invoke, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_raw(config_dir, {"schema_version": 1, "default_mode": "import"})
    before = config_file(config_dir).read_bytes()
    stub_editor(monkeypatch, "{ not json")
    result = invoke("config", "edit")
    assert result.code == EXIT_ATTENTION
    assert config_file(config_dir).read_bytes() == before


def test_edit_rejects_a_schema_violation_and_keeps_the_original(
    invoke: Invoke, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_raw(config_dir, {"schema_version": 1, "default_mode": "import"})
    before = config_file(config_dir).read_bytes()
    stub_editor(monkeypatch, '{"schema_version": 1, "default_mode": "sideways"}')
    result = invoke("config", "edit")
    assert result.code == EXIT_ATTENTION
    assert config_file(config_dir).read_bytes() == before


def test_edit_with_no_config_seeds_the_defaults(
    invoke: Invoke, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str] = {}

    def fake_run(argv: list[str], **_kw: object) -> object:
        seen["seed"] = Path(argv[-1]).read_text(encoding="utf-8")

        class Done:
            returncode = 0

        return Done()

    monkeypatch.setenv("EDITOR", "stub-editor")
    monkeypatch.setattr("subprocess.run", fake_run)
    invoke("config", "edit")
    assert json.loads(seen["seed"]) == {"schema_version": config_module.SCHEMA_VERSION}


def test_edit_with_no_editor_configured_is_refused(
    invoke: Invoke, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.delenv("VISUAL", raising=False)
    write_raw(config_dir, {"schema_version": 1})
    result = invoke("config", "edit")
    assert result.code == EXIT_ATTENTION
    assert "editor" in result.err


def test_edit_with_no_change_leaves_the_file_byte_identical(
    invoke: Invoke, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_raw(config_dir, {"schema_version": 1, "default_mode": "import"})
    before = config_file(config_dir).read_bytes()
    stub_editor(monkeypatch, None)
    result = invoke("config", "edit")
    assert result.code == EXIT_OK
    assert config_file(config_dir).read_bytes() == before


# --- section 8: end to end ---


def test_a_set_show_unset_show_round_trip(invoke: Invoke, config_dir: Path) -> None:
    invoke("config", "set", "default_mode", "copy")
    set_line = next(
        ln for ln in invoke("config", "show").out.splitlines() if "default_mode" in ln
    )
    assert "copy" in set_line and "set" in set_line
    invoke("config", "unset", "default_mode")
    unset_line = next(
        ln for ln in invoke("config", "show").out.splitlines() if "default_mode" in ln
    )
    assert "not-configured" in unset_line


def test_a_configured_library_path_is_read_by_snippet_list(
    invoke: Invoke, config_dir: Path, tmp_path: Path
) -> None:
    library = tmp_path / "elsewhere-lib"
    library.mkdir()
    (library / "house.md").write_text("---\ntitle: house\n---\n\nHouse rule.\n", encoding="utf-8")
    invoke("config", "set", "snippet_library_path", str(library))
    assert "house" in invoke("snippet", "list").out


def test_default_mode_changes_what_init_proposes(
    invoke: Invoke, config_dir: Path, tmp_path: Path
) -> None:
    library = config_dir / "snippets"
    library.mkdir(parents=True)
    (library / "base.md").write_text("---\ntitle: base\n---\n\nBase.\n", encoding="utf-8")
    invoke("config", "set", "default_mode", "copy")
    project = tmp_path / "fresh"
    project.mkdir()
    result = invoke("init", str(project), "--yes", "--snippets", "base")
    assert result.code == EXIT_OK
    assert "mode: copy" in result.out


def test_every_config_command_runs_non_interactively(invoke: Invoke, config_dir: Path) -> None:
    assert invoke("config", "show").code == EXIT_OK
    assert invoke("config", "set", "default_mode", "import").code == EXIT_OK
    assert invoke("config", "unset", "default_mode").code == EXIT_OK


def test_doctor_and_config_show_agree_on_the_config_path(
    invoke: Invoke, config_dir: Path
) -> None:
    doctor_line = next(
        ln for ln in invoke("doctor").out.splitlines() if "config file" in ln
    )
    show_line = next(
        ln for ln in invoke("config", "show").out.splitlines() if "config file" in ln
    )
    assert config_file(config_dir).as_posix() in doctor_line
    assert config_file(config_dir).as_posix() in show_line
