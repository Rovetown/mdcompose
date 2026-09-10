"""The eject command: marker removal, keep/strip, manifest deletion, state handling."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import Invocation

from mdcompose.core import managed_block
from mdcompose.core import platform as platform_module
from mdcompose.core.exit_codes import EXIT_ATTENTION, EXIT_OK

Invoke = Callable[..., Invocation]

AGENTS_BLOCK = managed_block.AGENTS_COMPOSITION_BLOCK
CLAUDE_BLOCK = managed_block.CLAUDE_MANAGED_BLOCK

SNIPPETS = {
    "overview": "---\ntitle: Overview\n---\n\nThis project is a CLI tool.\n",
    "claude-note": "---\ntitle: Claude note\napplies_to: claude\n---\n\nA Claude-only note.\n",
}


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_directory = tmp_path / "config"
    library = config_directory / "snippets"
    library.mkdir(parents=True)
    for name, text in SNIPPETS.items():
        (library / f"{name}.md").write_text(text, encoding="utf-8")
    monkeypatch.setattr(platform_module, "config_dir", lambda: config_directory)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return project


def library_files(workspace: Path) -> dict[str, bytes]:
    lib = workspace.parent / "config" / "snippets"
    return {p.name: p.read_bytes() for p in lib.iterdir()}


def composed(invoke: Invoke, workspace: Path, *snippets: str, mode: str = "copy") -> None:
    ids = ",".join(snippets) if snippets else "overview,claude-note"
    result = invoke("init", "--mode", mode, "--snippets", ids)
    assert result.code == EXIT_OK


def agents(workspace: Path) -> str:
    return (workspace / "AGENTS.md").read_text(encoding="utf-8")


def claude(workspace: Path) -> str:
    return (workspace / "CLAUDE.md").read_text(encoding="utf-8")


# --- section 1: marker removal ---


def test_no_marker_remains_after_an_eject(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace)
    result = invoke("eject", "--yes")
    assert result.code == EXIT_OK
    assert "mdcompose:" not in agents(workspace)
    assert "<!--" not in agents(workspace)
    assert "<!--" not in claude(workspace)


def test_markers_leave_no_blank_line_residue(invoke: Invoke, workspace: Path) -> None:
    (workspace / "AGENTS.md").write_text(
        f"# Head\n\ntext\n\n{managed_block.start_marker(AGENTS_BLOCK)}\nblock body\n"
        f"{managed_block.end_marker(AGENTS_BLOCK)}\n\nmore text\n",
        encoding="utf-8",
    )
    invoke("eject", "--yes")
    assert "\n\n\n" not in agents(workspace)


def test_a_second_eject_changes_nothing(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace)
    invoke("eject", "--yes")
    after_first = agents(workspace).encode()
    result = invoke("eject", "--yes")
    assert result.code == EXIT_OK
    assert agents(workspace).encode() == after_first


def test_line_endings_are_preserved(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace)
    path = workspace / "AGENTS.md"
    path.write_bytes(path.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
    invoke("eject", "--yes")
    assert b"\r\n" in path.read_bytes()


# --- section 2: keep and strip ---


def test_keep_is_the_default_and_leaves_the_content(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace)
    invoke("eject", "--yes")
    assert "This project is a CLI tool." in agents(workspace)


def test_import_mode_claude_keeps_its_directive_as_plain_markdown(
    invoke: Invoke, workspace: Path
) -> None:
    composed(invoke, workspace, "overview", mode="import")
    invoke("eject", "--yes")
    text = claude(workspace)
    assert "@AGENTS.md" in text
    assert "<!--" not in text


def test_strip_removes_the_block_content(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace)
    invoke("eject", "--strip", "--yes")
    assert "This project is a CLI tool." not in agents(workspace)


def test_strip_leaves_surrounding_prose_byte_identical(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace, "overview")
    existing = agents(workspace)
    (workspace / "AGENTS.md").write_text(f"Before.\n\n{existing}\nAfter.\n", encoding="utf-8")
    invoke("eject", "--strip", "--yes")
    text = agents(workspace)
    assert text.startswith("Before.")
    assert text.rstrip().endswith("After.")
    assert "This project is a CLI tool." not in text


def test_a_file_that_was_only_a_block_becomes_empty_not_deleted(
    invoke: Invoke, workspace: Path
) -> None:
    composed(invoke, workspace, "overview")
    invoke("eject", "--strip", "--yes")
    assert (workspace / "AGENTS.md").exists()
    assert agents(workspace).strip() == ""


# --- section 3: manifest deletion ---


def test_the_manifest_is_deleted(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace)
    invoke("eject", "--yes")
    assert not (workspace / "mdcompose.lock").exists()


def test_a_subdirectorys_manifest_is_untouched(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace)
    nested = workspace / "package"
    nested.mkdir()
    invoke("init", str(nested), "--mode", "copy", "--snippets", "overview")
    nested_lock = (nested / "mdcompose.lock").read_bytes()
    invoke("eject", "--yes")
    assert (nested / "mdcompose.lock").read_bytes() == nested_lock


def test_doctor_reports_uninitialized_after_an_eject(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace)
    invoke("eject", "--yes")
    result = invoke("doctor")
    assert result.code == EXIT_OK
    assert "not initialized" in result.out


def test_no_backup_file_is_written(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace)
    invoke("eject", "--yes")
    names = {p.name for p in workspace.iterdir()}
    assert names == {"AGENTS.md", "CLAUDE.md"}


# --- section 4: diff and confirmation ---


def test_the_diff_is_shown_and_declining_changes_nothing(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mdcompose.commands import eject_cmd

    composed(invoke, workspace)
    before = {p.name: p.read_bytes() for p in workspace.iterdir()}
    monkeypatch.setattr(eject_cmd, "is_interactive", lambda: True)
    monkeypatch.setattr("typer.confirm", lambda *_a, **_k: False)
    result = invoke("eject")
    assert result.code == EXIT_OK
    assert {p.name: p.read_bytes() for p in workspace.iterdir()} == before
    assert (workspace / "mdcompose.lock").exists()
    assert "@@" in result.out or "delete mdcompose.lock" in result.out


def test_yes_prints_the_diff_and_proceeds(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace)
    result = invoke("eject", "--yes")
    assert result.code == EXIT_OK
    assert "delete mdcompose.lock" in result.out


def test_nothing_to_eject_exits_zero(invoke: Invoke, workspace: Path) -> None:
    result = invoke("eject", "--yes")
    assert result.code == EXIT_OK
    assert "nothing to eject" in result.out


def test_eject_without_yes_and_no_terminal_is_refused(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace)
    result = invoke("eject")
    assert result.code == EXIT_ATTENTION
    assert "--yes" in result.err
    assert (workspace / "mdcompose.lock").exists()


# --- section 5: target directory handling ---


def test_an_explicit_directory_is_used_and_cwd_is_untouched(
    invoke: Invoke, workspace: Path
) -> None:
    composed(invoke, workspace)
    other = workspace.parent / "other"
    other.mkdir()
    invoke("init", str(other), "--mode", "copy", "--snippets", "overview")
    invoke("eject", str(other), "--yes")
    assert not (other / "mdcompose.lock").exists()
    assert (workspace / "mdcompose.lock").exists()


def test_a_missing_directory_is_refused(invoke: Invoke, workspace: Path) -> None:
    result = invoke("eject", str(workspace / "absent"), "--yes")
    assert result.code == EXIT_ATTENTION
    assert "absent" in result.err


# --- section 6: project state handling ---


def test_a_drifted_block_ejects_without_a_prompt(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace, "overview")
    edited = agents(workspace).replace("This project is a CLI tool.", "Hand edited.")
    (workspace / "AGENTS.md").write_text(edited, encoding="utf-8")
    result = invoke("eject", "--yes")
    assert result.code == EXIT_OK
    assert "Hand edited." in agents(workspace)
    assert "<!--" not in agents(workspace)


def test_a_malformed_block_stops_the_run_with_nothing_changed(
    invoke: Invoke, workspace: Path
) -> None:
    composed(invoke, workspace)
    (workspace / "AGENTS.md").write_text(
        f"{managed_block.start_marker(AGENTS_BLOCK)}\nunclosed\n", encoding="utf-8"
    )
    claude_before = claude(workspace).encode()
    result = invoke("eject", "--yes")
    assert result.code == EXIT_ATTENTION
    assert claude(workspace).encode() == claude_before
    assert (workspace / "mdcompose.lock").exists()


def test_a_manifest_recorded_file_that_vanished_is_skipped(
    invoke: Invoke, workspace: Path
) -> None:
    composed(invoke, workspace)
    (workspace / "CLAUDE.md").unlink()
    result = invoke("eject", "--yes")
    assert result.code == EXIT_OK
    assert not (workspace / "mdcompose.lock").exists()
    assert "CLAUDE.md" in result.err  # reported as skipped


def test_a_manifest_with_no_markers_still_deletes_the_manifest(
    invoke: Invoke, workspace: Path
) -> None:
    composed(invoke, workspace)
    (workspace / "AGENTS.md").write_text("# just prose\n", encoding="utf-8")
    (workspace / "CLAUDE.md").write_text("# just prose\n", encoding="utf-8")
    result = invoke("eject", "--yes")
    assert result.code == EXIT_OK
    assert not (workspace / "mdcompose.lock").exists()


def test_markers_with_no_manifest_are_still_removed(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace)
    (workspace / "mdcompose.lock").unlink()
    result = invoke("eject", "--yes")
    assert result.code == EXIT_OK
    assert "<!--" not in agents(workspace)


# --- section 7: untouched content ---


def test_imported_content_survives_an_eject(invoke: Invoke, workspace: Path) -> None:
    source = workspace.parent / "SRC.md"
    source.write_text("# Imported\n\none-off paste\n", encoding="utf-8")
    composed(invoke, workspace, "overview")
    invoke("import", str(source), "--section", "Imported")
    for extra in ([], ["--strip"]):
        invoke("eject", *extra, "--yes")
        assert "one-off paste" in agents(workspace)
        composed(invoke, workspace, "overview")  # re-compose for the next iteration


def test_hand_written_prose_around_a_block_survives(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace, "overview")
    existing = agents(workspace)
    wrapped = f"# My notes\n\nkeep this\n\n{existing}\ntrailing note\n"
    (workspace / "AGENTS.md").write_text(wrapped, encoding="utf-8")
    invoke("eject", "--strip", "--yes")
    text = agents(workspace)
    assert "# My notes" in text and "keep this" in text and "trailing note" in text


def test_converted_content_survives_an_eject(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace, "overview", mode="copy")
    (workspace / "CLAUDE.md").write_text(
        claude(workspace) + "\n# Claude prose\n\nmove me\n", encoding="utf-8"
    )
    invoke("convert", "CLAUDE.md", "AGENTS.md", "--section", "Claude prose", "--yes")
    invoke("eject", "--yes")
    assert "move me" in agents(workspace)


# --- section 8: global scope ---


@pytest.fixture
def global_workspace(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = workspace.parent / "home"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def test_global_eject_removes_markers_and_clears_the_record(
    invoke: Invoke, workspace: Path, global_workspace: Path
) -> None:
    agents_target = global_workspace / ".claude" / "AGENTS.md"
    setup = invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "overview",
        "--global-agents-path", str(agents_target),
    )
    assert setup.code == EXIT_OK
    result = invoke("eject", "--global", "--yes")
    assert result.code == EXIT_OK
    assert "<!--" not in agents_target.read_text(encoding="utf-8")
    from mdcompose.core import config as config_module

    loaded = config_module.load_config(
        config_module.config_path(workspace.parent / "config")
    )
    assert loaded.claude_global is None
    assert "global_snippet_ids" not in loaded.extra


def test_global_eject_leaves_unrelated_preferences(
    invoke: Invoke, workspace: Path, global_workspace: Path
) -> None:
    from mdcompose.core import config as config_module

    invoke("config", "set", "snippet_library_path", str(workspace.parent / "mylib"))
    agents_target = global_workspace / ".claude" / "AGENTS.md"
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "overview",
        "--global-agents-path", str(agents_target),
    )
    invoke("eject", "--global", "--yes")
    loaded = config_module.load_config(
        config_module.config_path(workspace.parent / "config")
    )
    assert loaded.snippet_library_path == (workspace.parent / "mylib").as_posix()


def test_global_eject_touches_no_project_file(
    invoke: Invoke, workspace: Path, global_workspace: Path
) -> None:
    composed(invoke, workspace)
    project_before = {p.name: p.read_bytes() for p in workspace.iterdir()}
    agents_target = global_workspace / ".claude" / "AGENTS.md"
    invoke(
        "init", "--global", "--yes", "--mode", "copy", "--snippets", "overview",
        "--global-agents-path", str(agents_target),
    )
    invoke("eject", "--global", "--yes")
    assert {p.name: p.read_bytes() for p in workspace.iterdir()} == project_before


# --- section 9: library safety ---


def test_a_project_eject_leaves_the_library_untouched(invoke: Invoke, workspace: Path) -> None:
    before = library_files(workspace)
    composed(invoke, workspace)
    invoke("eject", "--strip", "--yes")
    assert library_files(workspace) == before


def test_the_eject_prompt_never_offers_to_remove_snippets(
    invoke: Invoke, workspace: Path
) -> None:
    composed(invoke, workspace)
    result = invoke("eject", "--yes")
    assert "snippet" not in result.out.lower()
    assert "library" not in result.out.lower()


# --- section 10: end to end ---


def test_full_lifecycle_init_then_eject(invoke: Invoke, workspace: Path) -> None:
    composed(invoke, workspace, "overview")
    invoke("eject", "--yes")
    assert "This project is a CLI tool." in agents(workspace)
    assert "not initialized" in invoke("doctor").out


def test_eject_then_reinit_adds_a_fresh_block_beside_the_kept_content(
    invoke: Invoke, workspace: Path
) -> None:
    composed(invoke, workspace, "overview")
    invoke("eject", "--yes")
    composed(invoke, workspace, "overview")
    text = agents(workspace)
    assert text.count("This project is a CLI tool.") == 2  # kept paste + fresh block
    assert managed_block.read_blocks(workspace / "AGENTS.md").find(AGENTS_BLOCK) is not None


def test_eject_help_warns_it_is_not_a_toggle(invoke: Invoke, workspace: Path) -> None:
    assert "fresh" in invoke("eject", "--help").out.lower()
