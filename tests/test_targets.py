"""Registered global targets: config field, the target commands, projection, integrations."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import Invocation

from mdcompose.core import config as config_module
from mdcompose.core import managed_block
from mdcompose.core import platform as platform_module
from mdcompose.core import targets as targets_module
from mdcompose.core.exit_codes import EXIT_ATTENTION, EXIT_OK
from mdcompose.core.platform import PlatformInfo

Invoke = Callable[..., Invocation]

TARGET_BLOCK = managed_block.AGENTS_COMPOSITION_BLOCK
CLAUDE_BLOCK = managed_block.CLAUDE_MANAGED_BLOCK


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_directory = tmp_path / "config"
    library = config_directory / "snippets"
    library.mkdir(parents=True)
    (library / "conv.md").write_text(
        "---\ntitle: Conventions\napplies_to: agents\n---\n\nShared house style.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(platform_module, "config_dir", lambda: config_directory)
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.chdir(tmp_path)
    return fake_home


def config_file(home: Path) -> Path:
    return home.parent / "config" / "config.json"


def load(home: Path) -> config_module.GlobalConfig:
    return config_module.load_config(config_file(home))


def raw_config(home: Path, payload: dict) -> None:
    config_file(home).parent.mkdir(parents=True, exist_ok=True)
    config_file(home).write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))


def compose_global(invoke: Invoke, home: Path) -> Path:
    agents = home / ".claude" / "AGENTS.md"
    result = invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents),
    )
    assert result.code == EXIT_OK
    return agents


# --- section 1: config field ---


def test_two_targets_are_read(home: Path) -> None:
    raw_config(
        home,
        {
            "schema_version": 1,
            "registered_global_targets": [
                {"label": "codex", "path": "/home/u/.codex/AGENTS.md"},
                {"label": "cursor", "path": "/home/u/.cursor/rules.md", "mode": "copy"},
            ],
        },
    )
    targets = load(home).registered_global_targets
    assert [t.label for t in targets] == ["codex", "cursor"]
    assert targets[0].mode == "copy"


def test_an_absent_field_yields_no_targets(home: Path) -> None:
    raw_config(home, {"schema_version": 1})
    assert load(home).registered_global_targets == ()


@pytest.mark.parametrize(
    "entries",
    [
        "not-a-list",  # the field itself is not a list
        ["a bare string"],  # an entry is not an object
        [{"label": "a", "path": "/x/1"}, {"label": "a", "path": "/x/2"}],  # dup label
        [{"label": "a", "path": "/x/1"}, {"label": "b", "path": "/x/1"}],  # dup path
        [{"label": "", "path": "/x/1"}],  # empty label
        [{"label": "a", "path": "relative/path"}],  # relative
        [{"label": "a"}],  # incomplete
        [{"label": "a", "path": "/x/1", "mode": "import"}],  # import rejected
        [{"label": "a", "path": "/x/1", "mode": "sideways"}],  # unknown mode
        [{"label": "a", "path": "/x/1", "colour": "blue"}],  # unrecognized key
    ],
)
def test_an_invalid_targets_field_is_refused_on_read(home: Path, entries: object) -> None:
    raw_config(home, {"schema_version": 1, "registered_global_targets": entries})
    with pytest.raises(config_module.AttentionError):
        load(home)


def test_config_set_refuses_the_targets_field(invoke: Invoke, home: Path) -> None:
    result = invoke("config", "set", "registered_global_targets", "[]")
    assert result.code == EXIT_ATTENTION
    assert "target" in result.err


def test_config_show_lists_registered_targets(invoke: Invoke, home: Path) -> None:
    raw_config(
        home,
        {"schema_version": 1, "registered_global_targets": [{"label": "codex", "path": "/x/a"}]},
    )
    assert "codex" in invoke("config", "show").out


# --- section 2: target add ---


def test_target_add_records_the_entry(invoke: Invoke, home: Path) -> None:
    dest = home / ".codex" / "AGENTS.md"
    result = invoke("target", "add", "codex", str(dest))
    assert result.code == EXIT_OK
    targets = load(home).registered_global_targets
    assert targets[0].label == "codex"
    assert targets[0].path == dest.as_posix()


def test_target_add_writes_no_file(invoke: Invoke, home: Path) -> None:
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    assert not dest.exists()
    assert not dest.parent.exists()


def test_a_duplicate_label_is_refused(invoke: Invoke, home: Path) -> None:
    invoke("target", "add", "codex", str(home / ".codex" / "a.md"))
    result = invoke("target", "add", "codex", str(home / ".other" / "b.md"))
    assert result.code == EXIT_ATTENTION
    assert "codex" in result.err


def test_a_duplicate_path_is_refused(invoke: Invoke, home: Path) -> None:
    dest = home / ".codex" / "a.md"
    invoke("target", "add", "one", str(dest))
    result = invoke("target", "add", "two", str(dest))
    assert result.code == EXIT_ATTENTION
    assert "one" in result.err


def test_a_directory_path_is_refused(invoke: Invoke, home: Path) -> None:
    d = home / "adir"
    d.mkdir()
    result = invoke("target", "add", "codex", str(d))
    assert result.code == EXIT_ATTENTION
    assert "directory" in result.err


def test_the_canonical_path_cannot_be_a_target(invoke: Invoke, home: Path) -> None:
    canonical = home / ".claude" / "AGENTS.md"
    raw_config(home, {"schema_version": 1, "global_agents_path": canonical.as_posix()})
    result = invoke("target", "add", "self", str(canonical))
    assert result.code == EXIT_ATTENTION
    assert "canonical" in result.err


def test_target_add_warns_on_a_windows_mount(
    invoke: Invoke, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        platform_module, "detect_platform", lambda: PlatformInfo(os_name="linux", is_wsl=True)
    )
    result = invoke("target", "add", "codex", "/mnt/c/Users/x/.codex/AGENTS.md")
    assert result.code == EXIT_OK
    assert "/mnt/" in result.err
    assert load(home).registered_global_targets[0].label == "codex"


# --- section 3: target list ---


def test_target_list_shows_label_path_and_sync(invoke: Invoke, home: Path) -> None:
    agents = compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents),
    )
    out = invoke("target", "list").out
    assert "codex" in out
    assert "in-sync" in out


def test_target_list_with_none_registered(invoke: Invoke, home: Path) -> None:
    result = invoke("target", "list")
    assert result.code == EXIT_OK
    assert "no targets registered" in result.out


def test_target_list_json(invoke: Invoke, home: Path) -> None:
    compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    payload = json.loads(invoke("target", "list", "--json").out)
    entry = payload["targets"][0]
    assert set(entry) == {"label", "path", "present", "sync"}
    assert entry["label"] == "codex"


def test_sync_status_computation(home: Path) -> None:
    canonical = "## Conventions\n\nShared house style.\n"
    dest = home / ".codex" / "AGENTS.md"
    entry = config_module.TargetEntry(label="codex", path=dest.as_posix())
    assert targets_module.sync_status(entry, canonical) == "missing"
    dest.parent.mkdir(parents=True)
    dest.write_text(managed_block.upsert("", TARGET_BLOCK, canonical, dest), encoding="utf-8")
    assert targets_module.sync_status(entry, canonical) == "in-sync"
    dest.write_text(
        managed_block.upsert("", TARGET_BLOCK, "something else\n", dest), encoding="utf-8"
    )
    assert targets_module.sync_status(entry, canonical) == "out-of-sync"


def test_sync_status_is_out_of_sync_when_the_file_has_no_block(home: Path) -> None:
    dest = home / ".codex" / "AGENTS.md"
    dest.parent.mkdir(parents=True)
    dest.write_text("# Codex\n\nno managed block here\n", encoding="utf-8")
    entry = config_module.TargetEntry(label="codex", path=dest.as_posix())
    assert targets_module.sync_status(entry, "anything\n") == "out-of-sync"


def test_sync_status_is_malformed_when_the_markers_are_broken(home: Path) -> None:
    dest = home / ".codex" / "AGENTS.md"
    dest.parent.mkdir(parents=True)
    opening = managed_block.upsert("", TARGET_BLOCK, "body\n", dest).splitlines()[0]
    dest.write_text(f"{opening}\nbody with no closing marker\n", encoding="utf-8")
    entry = config_module.TargetEntry(label="codex", path=dest.as_posix())
    assert targets_module.sync_status(entry, "body\n") == "malformed"


# --- section 4: target remove ---


def test_target_remove_unregisters_and_leaves_the_file(invoke: Invoke, home: Path) -> None:
    agents = compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents),
    )
    file_before = dest.read_bytes()
    result = invoke("target", "remove", "codex")
    assert result.code == EXIT_OK
    assert "left in place" in result.out
    assert dest.read_bytes() == file_before
    assert load(home).registered_global_targets == ()


def test_removing_an_unknown_label_is_refused(invoke: Invoke, home: Path) -> None:
    result = invoke("target", "remove", "ghost")
    assert result.code == EXIT_ATTENTION
    assert "ghost" in result.err


# --- section 5: projection ---


def test_projection_writes_materialized_content_with_no_import_directive(
    invoke: Invoke, home: Path
) -> None:
    agents = compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    invoke(
        "init", "--global", "--yes", "--mode", "import", "--snippets", "conv",
        "--global-agents-path", str(agents),
    )
    text = dest.read_text(encoding="utf-8")
    assert "Shared house style." in text
    assert "@AGENTS.md" not in text
    assert "@../" not in text


def test_projection_creates_a_missing_target_with_only_its_block(
    invoke: Invoke, home: Path
) -> None:
    agents = compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents),
    )
    assert dest.is_file()
    blocks = managed_block.scan(dest.read_text(encoding="utf-8")).blocks
    assert len(blocks) == 1


def test_content_outside_a_target_block_survives_projection(invoke: Invoke, home: Path) -> None:
    agents = compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    dest.parent.mkdir(parents=True)
    dest.write_text("# Codex only\n\nforeign header\n\n(placeholder)\n\n# tail\n", encoding="utf-8")
    invoke("target", "add", "codex", str(dest))
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents),
    )
    text = dest.read_text(encoding="utf-8")
    assert "# Codex only" in text and "foreign header" in text and "# tail" in text
    assert "Shared house style." in text


def test_a_target_is_never_read_as_a_source(invoke: Invoke, home: Path) -> None:
    agents = compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents),
    )
    canonical_before = agents.read_bytes()
    dest.write_text(
        managed_block.upsert(dest.read_text(encoding="utf-8"), TARGET_BLOCK, "hijacked\n", dest),
        encoding="utf-8",
    )
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents), "--on-drift", "overwrite",
    )
    assert agents.read_bytes() == canonical_before


# --- section 6: projection failures are isolated ---


def _config_with_target(dest: Path) -> config_module.GlobalConfig:
    entry = config_module.TargetEntry(label="codex", path=dest.as_posix())
    return config_module.GlobalConfig(registered_global_targets=(entry,))


def test_project_skips_a_malformed_target_and_reports_failure(home: Path) -> None:
    dest = home / ".codex" / "AGENTS.md"
    dest.parent.mkdir(parents=True)
    opening = managed_block.upsert("", TARGET_BLOCK, "x\n", dest).splitlines()[0]
    dest.write_text(f"{opening}\nunterminated\n", encoding="utf-8")
    before = dest.read_bytes()

    result = targets_module.project(_config_with_target(dest), "canonical\n")

    assert result.had_failure
    assert result.outcomes[0].status == "skipped-malformed"
    assert dest.read_bytes() == before


def test_project_keeps_a_drifted_block_the_caller_did_not_resolve(home: Path) -> None:
    dest = home / ".codex" / "AGENTS.md"
    dest.parent.mkdir(parents=True)
    dest.write_text(managed_block.upsert("", TARGET_BLOCK, "hand-edited\n", dest), encoding="utf-8")

    result = targets_module.project(_config_with_target(dest), "canonical\n")

    assert not result.had_failure
    assert result.outcomes[0].status == "kept"
    assert "hand-edited" in dest.read_text(encoding="utf-8")


def test_project_skips_a_drifted_block_on_the_skip_choice(home: Path) -> None:
    dest = home / ".codex" / "AGENTS.md"
    dest.parent.mkdir(parents=True)
    dest.write_text(managed_block.upsert("", TARGET_BLOCK, "hand-edited\n", dest), encoding="utf-8")

    result = targets_module.project(
        _config_with_target(dest), "canonical\n", drift_choices={"codex": targets_module.SKIP}
    )

    assert result.outcomes[0].status == "kept"
    assert result.outcomes[0].detail == "skipped a drifted block"


def test_project_reports_an_unwritable_target(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = home / ".codex" / "AGENTS.md"

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(targets_module.files, "write_text", refuse)
    result = targets_module.project(_config_with_target(dest), "canonical\n")

    assert result.had_failure
    assert result.outcomes[0].status == "skipped-unwritable"


def test_add_target_resolves_a_relative_path_against_the_cwd(invoke: Invoke, home: Path) -> None:
    result = invoke("target", "add", "codex", "sub/AGENTS.md")
    assert result.code == EXIT_OK
    stored = load(home).registered_global_targets[0].path
    assert stored == (home.parent / "sub" / "AGENTS.md").as_posix()


# --- section 7: idempotence ---


def test_a_second_projection_leaves_targets_byte_identical(invoke: Invoke, home: Path) -> None:
    agents = compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    args = [
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents),
    ]
    invoke(*args)
    first = dest.read_bytes()
    invoke(*args)
    assert dest.read_bytes() == first


# --- section 8: doctor integration ---


def test_doctor_reports_targets_and_their_sync(invoke: Invoke, home: Path) -> None:
    agents = compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents),
    )
    result = invoke("doctor")
    assert result.code == EXIT_OK
    assert "codex" in result.out and "in-sync" in result.out


def test_doctor_exits_one_when_a_target_is_out_of_sync(invoke: Invoke, home: Path) -> None:
    agents = compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents),
    )
    dest.write_text(
        managed_block.upsert(dest.read_text(encoding="utf-8"), TARGET_BLOCK, "drifted\n", dest),
        encoding="utf-8",
    )
    result = invoke("doctor")
    assert result.code == EXIT_ATTENTION
    assert "out-of-sync" in result.out


def test_no_target_section_when_none_registered(invoke: Invoke, home: Path) -> None:
    result = invoke("doctor")
    assert result.code == EXIT_OK
    assert "registered targets" not in result.out


def test_targets_appear_in_doctor_json(invoke: Invoke, home: Path) -> None:
    compose_global(invoke, home)
    invoke("target", "add", "codex", str(home / ".codex" / "AGENTS.md"))
    payload = json.loads(invoke("doctor", "--json").out)
    assert payload["targets"][0]["label"] == "codex"


# --- section 9: eject integration ---


def test_global_eject_removes_target_blocks_but_keeps_registrations(
    invoke: Invoke, home: Path
) -> None:
    agents = compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents),
    )
    result = invoke("eject", "--global", "--yes")
    assert result.code == EXIT_OK
    assert "<!--" not in dest.read_text(encoding="utf-8")
    assert "Shared house style." in dest.read_text(encoding="utf-8")  # keep is default
    assert [t.label for t in load(home).registered_global_targets] == ["codex"]


def test_global_eject_strip_clears_target_content(invoke: Invoke, home: Path) -> None:
    agents = compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents),
    )
    invoke("eject", "--global", "--strip", "--yes")
    assert "Shared house style." not in dest.read_text(encoding="utf-8")


def test_a_project_eject_does_not_touch_a_target(invoke: Invoke, home: Path) -> None:
    agents = compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents),
    )
    target_before = dest.read_bytes()
    project = home.parent / "proj"
    project.mkdir()
    invoke("init", str(project), "--mode", "copy", "--snippets", "conv")
    invoke("eject", str(project), "--yes")
    assert dest.read_bytes() == target_before


# --- section 10: end to end ---


def test_full_lifecycle_register_project_doctor_eject(invoke: Invoke, home: Path) -> None:
    agents = compose_global(invoke, home)
    dest = home / ".codex" / "AGENTS.md"
    invoke("target", "add", "codex", str(dest))
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "conv",
        "--global-agents-path", str(agents),
    )
    block = managed_block.scan(dest.read_text(encoding="utf-8")).find(TARGET_BLOCK)
    assert block is not None and "Shared house style." in block.content
    assert invoke("doctor").code == EXIT_OK

    dest.write_text(
        managed_block.upsert(dest.read_text(encoding="utf-8"), TARGET_BLOCK, "hand\n", dest),
        encoding="utf-8",
    )
    assert invoke("doctor").code == EXIT_ATTENTION

    assert invoke("eject", "--global", "--yes").code == EXIT_OK
    assert load(home).claude_global is None
    assert [t.label for t in load(home).registered_global_targets] == ["codex"]
