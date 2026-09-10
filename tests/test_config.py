"""Reading the global config, and resolving the snippet library from it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mdcompose.core import config as config_module
from mdcompose.core.exit_codes import AttentionError

FULL_CONFIG = {
    "schema_version": 1,
    "snippet_library_path": "~/snippets",
    "default_mode": "import",
    "claude_global": {"path": "~/.claude/CLAUDE.md", "mode": "copy"},
    "global_agents_path": "~/.claude/AGENTS.md",
}


def write_config(directory: Path, payload: object) -> Path:
    target = config_module.config_path(directory)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_absent_config_leaves_every_field_unset(tmp_path: Path) -> None:
    configuration = config_module.load_config(config_module.config_path(tmp_path))
    assert configuration.exists is False
    assert configuration.schema_version is None
    assert configuration.snippet_library_path is None
    assert configuration.default_mode is None
    assert configuration.claude_global is None
    assert configuration.global_agents_path is None


def test_reading_an_absent_config_creates_nothing(tmp_path: Path) -> None:
    config_module.load_config(config_module.config_path(tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_full_config_is_read(tmp_path: Path) -> None:
    configuration = config_module.load_config(write_config(tmp_path, FULL_CONFIG))
    assert configuration.exists is True
    assert configuration.schema_version == 1
    assert configuration.snippet_library_path == "~/snippets"
    assert configuration.default_mode == "import"
    assert configuration.global_agents_path == "~/.claude/AGENTS.md"
    assert configuration.claude_global is not None
    assert configuration.claude_global.mode == "copy"


def test_unrecognized_field_is_preserved(tmp_path: Path) -> None:
    payload = dict(FULL_CONFIG) | {"future_option": {"nested": [1, 2]}}
    configuration = config_module.load_config(write_config(tmp_path, payload))
    assert configuration.extra == {"future_option": {"nested": [1, 2]}}
    assert configuration.default_mode == "import"


def test_unrecognized_nested_field_is_preserved(tmp_path: Path) -> None:
    payload = dict(FULL_CONFIG) | {"claude_global": {"path": "x", "mode": "copy", "future": 1}}
    configuration = config_module.load_config(write_config(tmp_path, payload))
    assert configuration.claude_global is not None
    assert configuration.claude_global.extra == {"future": 1}


def test_explicit_nulls_are_treated_as_unset(tmp_path: Path) -> None:
    payload = {"snippet_library_path": None, "default_mode": None, "global_agents_path": None}
    configuration = config_module.load_config(write_config(tmp_path, payload))
    assert configuration.snippet_library_path is None
    assert configuration.default_mode is None


def test_malformed_json_names_the_path(tmp_path: Path) -> None:
    target = config_module.config_path(tmp_path)
    target.write_text("{ not json", encoding="utf-8")
    with pytest.raises(AttentionError) as raised:
        config_module.load_config(target)
    assert "config.json" in str(raised.value)


def test_non_object_top_level_is_refused(tmp_path: Path) -> None:
    with pytest.raises(AttentionError) as raised:
        config_module.load_config(write_config(tmp_path, ["a", "list"]))
    assert "JSON object" in str(raised.value)


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"snippet_library_path": 7}, "snippet_library_path"),
        ({"global_agents_path": []}, "global_agents_path"),
        ({"schema_version": "one"}, "schema_version"),
        ({"schema_version": True}, "schema_version"),
        ({"claude_global": "not-an-object"}, "claude_global"),
    ],
)
def test_wrong_typed_field_names_the_field(tmp_path: Path, payload: dict, field: str) -> None:
    with pytest.raises(AttentionError) as raised:
        config_module.load_config(write_config(tmp_path, payload))
    assert field in str(raised.value)


def test_invalid_mode_lists_the_allowed_values(tmp_path: Path) -> None:
    with pytest.raises(AttentionError) as raised:
        config_module.load_config(write_config(tmp_path, {"default_mode": "sideways"}))
    message = str(raised.value)
    assert "sideways" in message
    assert "import" in message
    assert "copy" in message


def test_unreadable_config_is_reported(tmp_path: Path) -> None:
    """A path that exists but is not a file cannot be read as config."""
    target = config_module.config_path(tmp_path)
    target.mkdir(parents=True)
    with pytest.raises(AttentionError) as raised:
        config_module.load_config(target)
    assert "config.json" in str(raised.value)


def test_library_defaults_inside_the_config_directory(tmp_path: Path) -> None:
    configuration = config_module.load_config(config_module.config_path(tmp_path))
    assert config_module.library_dir(configuration, tmp_path) == tmp_path / "snippets"


def test_configured_library_path_wins(tmp_path: Path) -> None:
    configuration = config_module.load_config(
        write_config(tmp_path, {"snippet_library_path": str(tmp_path / "elsewhere")})
    )
    assert config_module.library_dir(configuration, tmp_path) == tmp_path / "elsewhere"


def test_library_resolution_creates_nothing(tmp_path: Path) -> None:
    configuration = config_module.load_config(config_module.config_path(tmp_path))
    resolved = config_module.library_dir(configuration, tmp_path)
    assert resolved.exists() is False
    assert list(tmp_path.iterdir()) == []


def test_explicit_library_path_is_flagged_as_chosen(tmp_path: Path) -> None:
    unset = config_module.load_config(config_module.config_path(tmp_path))
    assert unset.library_path_is_explicit is False
    chosen = config_module.load_config(
        write_config(tmp_path, {"snippet_library_path": "~/snippets"})
    )
    assert chosen.library_path_is_explicit is True


# --- section 1: validation for config set / unset ---

EMPTY = config_module.GlobalConfig()


def test_set_a_top_level_mode() -> None:
    updated = config_module.apply_set(EMPTY, "default_mode", "copy")
    assert updated.default_mode == "copy"


def test_set_a_nested_mode() -> None:
    updated = config_module.apply_set(EMPTY, "claude_global.mode", "import")
    assert updated.claude_global is not None
    assert updated.claude_global.mode == "import"


def test_an_invalid_mode_value_names_the_field_and_the_options() -> None:
    with pytest.raises(AttentionError, match="default_mode") as caught:
        config_module.apply_set(EMPTY, "default_mode", "sideways")
    assert "import" in caught.value.message and "copy" in caught.value.message


def test_an_invalid_nested_mode_value_is_refused() -> None:
    with pytest.raises(AttentionError, match=r"claude_global\.mode"):
        config_module.apply_set(EMPTY, "claude_global.mode", "sideways")


def test_an_unknown_key_is_named_and_refused() -> None:
    with pytest.raises(AttentionError, match="not a recognized config field"):
        config_module.apply_set(EMPTY, "colour_scheme", "dark")


def test_schema_version_is_not_settable() -> None:
    with pytest.raises(AttentionError, match="not user-settable"):
        config_module.apply_set(EMPTY, "schema_version", "2")


def test_a_tilde_path_is_stored_expanded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    updated = config_module.apply_set(EMPTY, "snippet_library_path", "~/snippets")
    assert updated.snippet_library_path == (tmp_path / "snippets").as_posix()
    assert "~" not in updated.snippet_library_path


def test_a_relative_path_is_stored_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    updated = config_module.apply_set(EMPTY, "global_agents_path", "shared/AGENTS.md")
    assert Path(updated.global_agents_path).is_absolute()


def test_a_nested_path_field_is_validated_and_expanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    updated = config_module.apply_set(EMPTY, "claude_global.path", "~/.claude/CLAUDE.md")
    assert updated.claude_global is not None
    assert Path(updated.claude_global.path).is_absolute()


def test_unset_removes_a_field() -> None:
    started = config_module.GlobalConfig(default_mode="copy")
    assert config_module.apply_unset(started, "default_mode").default_mode is None


def test_unset_the_last_nested_field_drops_the_object() -> None:
    started = config_module.GlobalConfig(claude_global=config_module.ClaudeGlobal(mode="import"))
    assert config_module.apply_unset(started, "claude_global.mode").claude_global is None


def test_unset_an_unknown_key_is_refused() -> None:
    with pytest.raises(AttentionError, match="not a recognized config field"):
        config_module.apply_unset(EMPTY, "nope")


def test_a_dotted_set_keeps_a_sibling_nested_value() -> None:
    started = config_module.GlobalConfig(
        claude_global=config_module.ClaudeGlobal(path="/x/CLAUDE.md")
    )
    updated = config_module.apply_set(started, "claude_global.mode", "copy")
    assert updated.claude_global is not None
    assert updated.claude_global.path == "/x/CLAUDE.md"
    assert updated.claude_global.mode == "copy"


# --- section 2: atomic write ---


def config_at(directory: Path) -> Path:
    return config_module.config_path(directory)


def test_a_successful_write_produces_the_rendered_config(tmp_path: Path) -> None:
    config_module.write_config(
        config_module.GlobalConfig(default_mode="copy"), config_at(tmp_path)
    )
    document = json.loads(config_at(tmp_path).read_text(encoding="utf-8"))
    assert document == {"schema_version": 1, "default_mode": "copy"}


def test_an_interrupted_write_leaves_the_previous_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = config_at(tmp_path)
    config_module.write_config(config_module.GlobalConfig(default_mode="import"), target)
    before = target.read_bytes()

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(config_module.files, "write_text", boom)
    with pytest.raises(OSError, match="disk full"):
        config_module.write_config(config_module.GlobalConfig(default_mode="copy"), target)
    assert target.read_bytes() == before


def test_no_temporary_artifact_survives_a_failed_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = config_at(tmp_path)
    config_module.write_config(config_module.GlobalConfig(), target)
    real = config_module.files.write_text

    def partial_then_fail(path: Path, text: str, **kw: object) -> None:
        real(path, text[: len(text) // 2], **kw)
        raise OSError("interrupted")

    monkeypatch.setattr(config_module.files, "write_text", partial_then_fail)
    with pytest.raises(OSError, match="interrupted"):
        config_module.write_config(config_module.GlobalConfig(default_mode="copy"), target)
    assert [p.name for p in tmp_path.iterdir()] == [target.name]


def test_a_shorter_config_replaces_a_longer_one_completely(tmp_path: Path) -> None:
    target = config_at(tmp_path)
    config_module.write_config(
        config_module.GlobalConfig(
            snippet_library_path="/a/very/long/path/to/snippets",
            default_mode="import",
            global_agents_path="/another/long/path/AGENTS.md",
        ),
        target,
    )
    config_module.write_config(config_module.GlobalConfig(default_mode="copy"), target)
    text = target.read_text(encoding="utf-8")
    assert "snippets" not in text and "AGENTS.md" not in text
    assert json.loads(text) == {"schema_version": 1, "default_mode": "copy"}


def test_rename_over_an_existing_config_works_on_this_platform(tmp_path: Path) -> None:
    """2.5 for the platform running the suite. CI covers the others."""
    target = config_at(tmp_path)
    for mode in ("import", "copy", "import"):
        config_module.write_config(config_module.GlobalConfig(default_mode=mode), target)
        assert json.loads(target.read_text(encoding="utf-8"))["default_mode"] == mode


# --- section 3: unrecognized field preservation ---


def reload(directory: Path) -> config_module.GlobalConfig:
    return config_module.load_config(config_at(directory))


def test_an_unknown_field_survives_a_set(tmp_path: Path) -> None:
    write_config(tmp_path, {"schema_version": 1, "future_setting": "keep me"})
    updated = config_module.apply_set(reload(tmp_path), "default_mode", "copy")
    config_module.write_config(updated, config_at(tmp_path))
    document = json.loads(config_at(tmp_path).read_text(encoding="utf-8"))
    assert document["future_setting"] == "keep me"
    assert document["default_mode"] == "copy"


def test_an_unknown_field_survives_an_unset(tmp_path: Path) -> None:
    write_config(
        tmp_path, {"schema_version": 1, "default_mode": "import", "future_setting": "keep me"}
    )
    updated = config_module.apply_unset(reload(tmp_path), "default_mode")
    config_module.write_config(updated, config_at(tmp_path))
    document = json.loads(config_at(tmp_path).read_text(encoding="utf-8"))
    assert document["future_setting"] == "keep me"
    assert "default_mode" not in document


def test_a_config_with_several_unknown_fields_round_trips_losslessly(tmp_path: Path) -> None:
    original = {
        "schema_version": 1,
        "default_mode": "copy",
        "future_scalar": 7,
        "future_object": {"a": 1, "b": [2, 3]},
        "claude_global": {"mode": "import", "future_nested": "x"},
    }
    write_config(tmp_path, original)
    config_module.write_config(reload(tmp_path), config_at(tmp_path))
    assert json.loads(config_at(tmp_path).read_text(encoding="utf-8")) == original


# --- section 4: first write creates the config ---


def test_first_write_creates_the_file_and_its_directory(tmp_path: Path) -> None:
    directory = tmp_path / "no" / "config" / "dir"
    assert not directory.exists()
    target = config_at(directory)
    config_module.write_config(config_module.GlobalConfig(default_mode="copy"), target)
    assert target.is_file()


def test_a_created_config_records_the_current_schema_version(tmp_path: Path) -> None:
    config_module.write_config(config_module.GlobalConfig(), config_at(tmp_path))
    document = json.loads(config_at(tmp_path).read_text(encoding="utf-8"))
    assert document["schema_version"] == config_module.SCHEMA_VERSION
