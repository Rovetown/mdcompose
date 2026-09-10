"""Composition: modes, ordering, target directories, drift, manifest writing."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import Invocation

from mdcompose.core import composition, files, managed_block
from mdcompose.core import manifest as manifest_module
from mdcompose.core import platform as platform_module
from mdcompose.core import snippets as snippets_module
from mdcompose.core.exit_codes import EXIT_ATTENTION, EXIT_OK

Invoke = Callable[..., Invocation]

AGENTS_BLOCK = managed_block.AGENTS_COMPOSITION_BLOCK
CLAUDE_BLOCK = managed_block.CLAUDE_MANAGED_BLOCK

SNIPPET_FILES = {
    "overview": (
        "---\ntitle: Overview\ncategory: overview\norder: 1\n"
        "stack_signals: [pyproject.toml]\n---\n\nThis project is a CLI tool.\n"
    ),
    "agents-only": (
        "---\ntitle: Agents only\napplies_to: agents\ncategory: conventions\n---\n\n"
        "Applies to every agent.\n"
    ),
    "claude-only": (
        "---\ntitle: Claude only\napplies_to: claude\ncategory: conventions\n---\n\n"
        "Claude specific note.\n"
    ),
}


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A populated library and an empty project, isolated from the machine."""
    config_directory = tmp_path / "config"
    library = config_directory / "snippets"
    library.mkdir(parents=True)
    for name, text in SNIPPET_FILES.items():
        (library / f"{name}.md").write_text(text, encoding="utf-8")
    monkeypatch.setattr(platform_module, "config_dir", lambda: config_directory)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return project


def block_of(path: Path, block_id: str) -> str:
    found = managed_block.read_blocks(path).find(block_id)
    assert found is not None, f"no {block_id} block in {path}"
    return found.content


def read_manifest(root: Path) -> manifest_module.Manifest:
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(root))
    assert manifest is not None
    return manifest


ALL = "overview,agents-only,claude-only"


def test_import_mode_points_claude_at_agents(invoke: Invoke, workspace: Path) -> None:
    result = invoke("init", "--mode", "import", "--snippets", ALL)
    assert result.code == EXIT_OK
    assert block_of(workspace / "CLAUDE.md", CLAUDE_BLOCK).strip() == "@AGENTS.md"


def test_import_mode_does_not_duplicate_the_content(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    claude = block_of(workspace / "CLAUDE.md", CLAUDE_BLOCK)
    assert "This project is a CLI tool." not in claude


def test_copy_mode_materializes_the_content(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "copy", "--snippets", ALL)
    claude = block_of(workspace / "CLAUDE.md", CLAUDE_BLOCK)
    assert "This project is a CLI tool." in claude
    assert "Claude specific note." in claude


def test_agents_md_never_carries_an_import_directive(invoke: Invoke, workspace: Path) -> None:
    """AGENTS.md stays plain markdown, because no other tool resolves @import."""
    for mode in (composition.IMPORT, composition.COPY):
        invoke("init", "--mode", mode, "--snippets", ALL)
        assert "@AGENTS.md" not in (workspace / "AGENTS.md").read_text(encoding="utf-8")


def test_agents_md_is_identical_across_modes(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    with_import = (workspace / "AGENTS.md").read_bytes()
    invoke("init", "--mode", "copy", "--snippets", ALL)
    assert (workspace / "AGENTS.md").read_bytes() == with_import


def test_applies_to_decides_which_file_gets_a_snippet(
    invoke: Invoke, workspace: Path
) -> None:
    invoke("init", "--mode", "copy", "--snippets", ALL)
    agents = block_of(workspace / "AGENTS.md", AGENTS_BLOCK)
    claude = block_of(workspace / "CLAUDE.md", CLAUDE_BLOCK)
    assert "Applies to every agent." in agents
    assert "Applies to every agent." not in claude
    assert "Claude specific note." in claude
    assert "Claude specific note." not in agents


def test_a_mode_switch_reuses_the_same_block(invoke: Invoke, workspace: Path) -> None:
    """Mode-specific ids would leave the old block behind as orphaned content."""
    invoke("init", "--mode", "import", "--snippets", ALL)
    invoke("init", "--mode", "copy", "--snippets", ALL)
    text = (workspace / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.count(managed_block.start_marker(CLAUDE_BLOCK)) == 1


def test_an_invalid_mode_lists_the_options(invoke: Invoke, workspace: Path) -> None:
    result = invoke("init", "--mode", "sideways", "--snippets", ALL)
    assert result.code == EXIT_ATTENTION
    assert "import" in result.err


def test_the_mode_is_remembered(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "copy", "--snippets", ALL)
    result = invoke("init", "--snippets", ALL)
    assert result.code == EXIT_OK
    assert "mode: copy" in result.out


def test_a_mode_flag_overrides_what_was_recorded(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "copy", "--snippets", ALL)
    result = invoke("init", "--mode", "import", "--snippets", ALL)
    assert "mode: import" in result.out
    assert read_manifest(workspace).files["claude_md"].mode == "import"


def test_repeated_runs_are_idempotent(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    before = {name: (workspace / name).read_bytes() for name in ("AGENTS.md", "CLAUDE.md")}
    result = invoke("init", "--mode", "import", "--snippets", ALL)
    after = {name: (workspace / name).read_bytes() for name in ("AGENTS.md", "CLAUDE.md")}
    assert after == before
    assert "unchanged" in result.out


def test_prose_outside_the_block_survives(invoke: Invoke, workspace: Path) -> None:
    (workspace / "AGENTS.md").write_text(
        "# My own heading\n\nHand written prose.\n", encoding="utf-8"
    )
    invoke("init", "--mode", "import", "--snippets", ALL)
    text = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert "# My own heading" in text
    assert "Hand written prose." in text
    assert "This project is a CLI tool." in text


def test_prose_on_both_sides_of_the_block_survives(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    existing = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    (workspace / "AGENTS.md").write_text(
        f"Before.\n\n{existing}\nAfter.\n", encoding="utf-8"
    )
    invoke("init", "--mode", "import", "--snippets", "overview")
    text = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith("Before.")
    assert "After." in text


def test_an_existing_crlf_file_keeps_its_line_endings(invoke: Invoke, workspace: Path) -> None:
    (workspace / "AGENTS.md").write_bytes(b"# Heading\r\n\r\nProse.\r\n")
    invoke("init", "--mode", "import", "--snippets", ALL)
    assert b"\r\n" in (workspace / "AGENTS.md").read_bytes()


def test_a_new_file_uses_line_feeds(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    assert b"\r\n" not in (workspace / "AGENTS.md").read_bytes()


def test_an_explicit_target_directory_is_used(invoke: Invoke, workspace: Path) -> None:
    other = workspace.parent / "other"
    other.mkdir()
    result = invoke("init", str(other), "--mode", "import", "--snippets", "overview")
    assert result.code == EXIT_OK
    assert (other / "AGENTS.md").exists()
    assert not (workspace / "AGENTS.md").exists()


def test_a_missing_target_directory_is_refused(invoke: Invoke, workspace: Path) -> None:
    result = invoke("init", str(workspace / "absent"), "--mode", "import", "--snippets", "overview")
    assert result.code == EXIT_ATTENTION
    assert "not a directory" in result.err


def test_a_stray_snippet_id_as_directory_hints_at_the_snippets_flag(
    invoke: Invoke, workspace: Path
) -> None:
    result = invoke("init", "python-style", "--mode", "import")
    assert result.code == EXIT_ATTENTION
    assert "--snippets" in result.err
    assert "quoted" in result.err


def test_each_directory_has_its_own_manifest(invoke: Invoke, workspace: Path) -> None:
    nested = workspace / "package"
    nested.mkdir()
    invoke("init", "--mode", "import", "--snippets", ALL)
    parent_before = manifest_module.manifest_path(workspace).read_bytes()
    invoke("init", str(nested), "--mode", "copy", "--snippets", "overview")
    assert manifest_module.manifest_path(nested).exists()
    assert manifest_module.manifest_path(workspace).read_bytes() == parent_before


def test_a_subdirectory_does_not_inherit_the_parent_selection(
    invoke: Invoke, workspace: Path
) -> None:
    nested = workspace / "package"
    nested.mkdir()
    invoke("init", "--mode", "import", "--snippets", ALL)
    invoke("init", str(nested), "--mode", "import", "--snippets", "overview")
    assert [entry.id for entry in read_manifest(nested).snippets] == ["overview"]


def test_a_subdirectory_can_import_the_root_agents_md(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    nested = workspace / "package"
    nested.mkdir()
    result = invoke(
        "init",
        str(nested),
        "--mode",
        "import",
        "--snippets",
        "overview",
        "--agents-from",
        str(workspace / "AGENTS.md"),
    )
    assert result.code == EXIT_OK
    assert block_of(nested / "CLAUDE.md", CLAUDE_BLOCK).strip() == "@../AGENTS.md"


def test_an_alternate_import_source_is_not_rewritten(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    before = (workspace / "AGENTS.md").read_bytes()
    nested = workspace / "package"
    nested.mkdir()
    invoke(
        "init",
        str(nested),
        "--mode",
        "import",
        "--snippets",
        "overview",
        "--agents-from",
        str(workspace / "AGENTS.md"),
    )
    assert (workspace / "AGENTS.md").read_bytes() == before
    assert not (nested / "AGENTS.md").exists()


def test_an_absent_alternate_import_source_is_refused(invoke: Invoke, workspace: Path) -> None:
    result = invoke(
        "init", "--mode", "import", "--snippets", "overview", "--agents-from", "nowhere/AGENTS.md"
    )
    assert result.code == EXIT_ATTENTION
    assert "no AGENTS.md" in result.err


def test_an_alternate_import_source_is_rejected_in_copy_mode(
    invoke: Invoke, workspace: Path
) -> None:
    """Copy mode materializes content, so it has no reason to point elsewhere."""
    (workspace / "elsewhere.md").write_text("x\n", encoding="utf-8")
    result = invoke(
        "init", "--mode", "copy", "--snippets", "overview", "--agents-from", "elsewhere.md"
    )
    assert result.code == EXIT_ATTENTION
    assert "import mode" in result.err


def test_stack_signals_are_detected_by_presence(invoke: Invoke, workspace: Path) -> None:
    (workspace / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    result = invoke("init", "--yes")
    assert "detected: pyproject.toml" in result.out
    assert read_manifest(workspace).detected_stack == ("pyproject.toml",)


def test_the_scan_reads_no_file_contents(invoke: Invoke, workspace: Path) -> None:
    """Presence only. Parsing a manifest would inherit every version of it."""
    (workspace / "pyproject.toml").write_bytes(b"\xff\xfe not parseable at all")
    result = invoke("init", "--yes")
    assert result.code == EXIT_OK
    assert "detected: pyproject.toml" in result.out


def test_accepting_detected_snippets_composes_them(invoke: Invoke, workspace: Path) -> None:
    (workspace / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    invoke("init", "--yes")
    assert [entry.id for entry in read_manifest(workspace).snippets] == ["overview"]


def test_no_signals_detected_is_not_an_error(invoke: Invoke, workspace: Path) -> None:
    result = invoke("init", "--yes")
    assert result.code == EXIT_OK
    assert "snippets: none" in result.out


def test_an_unknown_snippet_id_is_named(invoke: Invoke, workspace: Path) -> None:
    result = invoke("init", "--mode", "import", "--snippets", "absent")
    assert result.code == EXIT_ATTENTION
    assert "absent" in result.err


def test_an_empty_selection_writes_empty_blocks(invoke: Invoke, workspace: Path) -> None:
    result = invoke("init", "--mode", "import", "--snippets", "")
    assert result.code == EXIT_OK
    assert block_of(workspace / "AGENTS.md", AGENTS_BLOCK) == ""


def test_an_empty_library_with_nothing_recorded_is_refused(
    invoke: Invoke, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform_module, "config_dir", lambda: tmp_path / "empty-config")
    project = tmp_path / "bare"
    project.mkdir()
    monkeypatch.chdir(project)
    result = invoke("init", "--mode", "import")
    assert result.code == EXIT_ATTENTION
    assert "empty" in result.err


def test_re_running_uses_the_recorded_selection_when_there_is_no_picker(
    invoke: Invoke, workspace: Path
) -> None:
    """Recorded selections beat detection, so the tool never argues with the user."""
    (workspace / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    invoke("init", "--mode", "import", "--snippets", "agents-only")
    result = invoke("init")
    assert result.code == EXIT_OK
    assert [entry.id for entry in read_manifest(workspace).snippets] == ["agents-only"]


def test_reapply_recomposes_from_the_recorded_selection_and_mode(
    invoke: Invoke, workspace: Path
) -> None:
    (workspace / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    invoke("init", "--mode", "copy", "--snippets", "agents-only")
    result = invoke("init", "--reapply")
    assert result.code == EXIT_OK
    assert "mode: copy" in result.out
    assert [entry.id for entry in read_manifest(workspace).snippets] == ["agents-only"]


def test_reapply_does_not_re_add_a_detected_snippet(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", "agents-only")
    # pyproject.toml would make detection suggest 'overview'
    (workspace / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    invoke("init", "--reapply")
    assert [entry.id for entry in read_manifest(workspace).snippets] == ["agents-only"]


def test_reapply_without_a_manifest_is_refused(invoke: Invoke, workspace: Path) -> None:
    result = invoke("init", "--reapply")
    assert result.code == EXIT_ATTENTION
    assert "no mdcompose.lock" in result.err


def test_deselecting_removes_content_and_the_record(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "copy", "--snippets", ALL)
    invoke("init", "--mode", "copy", "--snippets", "overview")
    assert "Applies to every agent." not in block_of(workspace / "AGENTS.md", AGENTS_BLOCK)
    assert [entry.id for entry in read_manifest(workspace).snippets] == ["overview"]


def test_the_manifest_records_everything(invoke: Invoke, workspace: Path) -> None:
    (workspace / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    invoke("init", "--mode", "import", "--snippets", ALL)
    manifest = read_manifest(workspace)
    assert manifest.schema_version == manifest_module.SCHEMA_VERSION
    assert manifest.generated_by is not None and "mdcompose" in manifest.generated_by
    assert manifest.generated_at is not None
    assert manifest.detected_stack == ("pyproject.toml",)
    assert [entry.id for entry in manifest.snippets_in_order()] == ALL.split(",")
    assert manifest.files["claude_md"].imports == "AGENTS.md"


def test_the_recorded_hash_matches_what_was_written(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "copy", "--snippets", ALL)
    manifest = read_manifest(workspace)
    for key, name in (("agents_md", "AGENTS.md"), ("claude_md", "CLAUDE.md")):
        block_id = manifest_module.BLOCK_ID_BY_KEY[key]
        actual = files.hash_content(block_of(workspace / name, block_id))
        assert manifest.files[key].managed_block_hash == actual


def test_the_manifest_records_nothing_machine_specific(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    raw = manifest_module.manifest_path(workspace).read_text(encoding="utf-8")
    document = json.loads(raw)
    assert document["files"]["agents_md"]["path"] == "AGENTS.md"
    for forbidden in (str(workspace), "os_at_last_sync", "wsl_at_last_sync", "hostname"):
        assert forbidden not in raw


def test_the_manifest_is_readable_in_a_diff(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    raw = manifest_module.manifest_path(workspace).read_text(encoding="utf-8")
    assert raw.count("\n") > 10
    assert raw.endswith("\n")


def test_no_gitignore_is_created_or_changed(invoke: Invoke, workspace: Path) -> None:
    """The manifest is committed by design, so there is nothing to ignore."""
    invoke("init", "--mode", "import", "--snippets", ALL)
    assert not (workspace / ".gitignore").exists()


def test_doctor_reports_clean_immediately_after_init(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    result = invoke("doctor")
    assert result.code == EXIT_OK
    assert "drifted" not in result.out


def test_a_hand_edit_is_reported_before_writing(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    edited = (workspace / "AGENTS.md").read_text(encoding="utf-8").replace(
        "This project is a CLI tool.", "Hand edited."
    )
    (workspace / "AGENTS.md").write_text(edited, encoding="utf-8")
    result = invoke("init", "--mode", "import", "--snippets", ALL)
    assert result.code == EXIT_ATTENTION
    assert "--on-drift" in result.err


def test_keeping_a_hand_edit_leaves_it_and_records_it(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    edited = (workspace / "AGENTS.md").read_text(encoding="utf-8").replace(
        "This project is a CLI tool.", "Hand edited."
    )
    (workspace / "AGENTS.md").write_text(edited, encoding="utf-8")
    result = invoke("init", "--mode", "import", "--snippets", ALL, "--on-drift", "keep")
    assert result.code == EXIT_OK
    assert "Hand edited." in block_of(workspace / "AGENTS.md", AGENTS_BLOCK)
    assert invoke("doctor").code == EXIT_OK


def test_overwriting_a_hand_edit_replaces_it(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    edited = (workspace / "AGENTS.md").read_text(encoding="utf-8").replace(
        "This project is a CLI tool.", "Hand edited."
    )
    (workspace / "AGENTS.md").write_text(edited, encoding="utf-8")
    invoke("init", "--mode", "import", "--snippets", ALL, "--on-drift", "overwrite")
    assert "This project is a CLI tool." in block_of(workspace / "AGENTS.md", AGENTS_BLOCK)


def test_aborting_writes_nothing(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    edited = (workspace / "AGENTS.md").read_text(encoding="utf-8").replace(
        "This project is a CLI tool.", "Hand edited."
    )
    (workspace / "AGENTS.md").write_text(edited, encoding="utf-8")
    before = {
        name: (workspace / name).read_bytes()
        for name in ("AGENTS.md", "CLAUDE.md", "mdcompose.lock")
    }
    result = invoke("init", "--mode", "import", "--snippets", ALL, "--on-drift", "abort")
    assert result.code == EXIT_ATTENTION
    after = {
        name: (workspace / name).read_bytes()
        for name in ("AGENTS.md", "CLAUDE.md", "mdcompose.lock")
    }
    assert after == before


def test_an_invalid_drift_choice_lists_the_options(invoke: Invoke, workspace: Path) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    (workspace / "AGENTS.md").write_text(
        (workspace / "AGENTS.md").read_text(encoding="utf-8").replace("CLI tool", "edited"),
        encoding="utf-8",
    )
    result = invoke("init", "--mode", "import", "--snippets", ALL, "--on-drift", "sideways")
    assert result.code == EXIT_ATTENTION
    assert "overwrite" in result.err


def test_malformed_markers_stop_the_run_before_writing(invoke: Invoke, workspace: Path) -> None:
    """Harsher than drift: with broken markers mdcompose cannot tell which bytes
    it owns, so any write risks destroying user content."""
    invoke("init", "--mode", "import", "--snippets", ALL)
    (workspace / "AGENTS.md").write_text(
        f"{managed_block.start_marker(AGENTS_BLOCK)}\ncontent\n", encoding="utf-8"
    )
    before = (workspace / "CLAUDE.md").read_bytes()
    result = invoke("init", "--mode", "import", "--snippets", ALL)
    assert result.code == EXIT_ATTENTION
    assert "Fix the markers" in result.err
    assert (workspace / "CLAUDE.md").read_bytes() == before


def clone_of(workspace: Path, destination: Path) -> Path:
    """A checkout carrying only the committed manifest, as a clone would."""
    destination.mkdir()
    (destination / manifest_module.MANIFEST_FILENAME).write_bytes(
        manifest_module.manifest_path(workspace).read_bytes()
    )
    return destination


def test_a_clone_refuses_to_compose_without_confirmation(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The trust boundary: that markdown came from somebody else."""
    invoke("init", "--mode", "import", "--snippets", ALL)
    clone = clone_of(workspace, workspace.parent / "clone")
    monkeypatch.chdir(clone)
    result = invoke("init")
    assert result.code == EXIT_ATTENTION
    assert not (clone / "AGENTS.md").exists()


def test_a_confirmed_clone_composes_from_embedded_content(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    clone = clone_of(workspace, workspace.parent / "clone")
    monkeypatch.setattr(platform_module, "config_dir", lambda: tmp_path / "no-library")
    monkeypatch.chdir(clone)
    result = invoke("init", "--yes")
    assert result.code == EXIT_OK
    assert "This project is a CLI tool." in block_of(clone / "AGENTS.md", AGENTS_BLOCK)


def test_a_clone_with_an_empty_library_still_composes(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Embedded content is what makes a fork by a stranger reproduce the files.

    A regression guard: --yes once meant both "confirm" and "use the detected
    snippets instead", which silently composed an empty block here.
    """
    invoke("init", "--mode", "copy", "--snippets", ALL)
    clone = clone_of(workspace, workspace.parent / "clone")
    monkeypatch.setattr(platform_module, "config_dir", lambda: tmp_path / "no-library")
    monkeypatch.chdir(clone)
    invoke("init", "--yes")
    assert snippets_module.load_library(tmp_path / "no-library" / "snippets") == ()
    assert "Claude specific note." in block_of(clone / "CLAUDE.md", CLAUDE_BLOCK)


def test_composing_a_clone_adopts_nothing_into_the_library(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    invoke("init", "--mode", "import", "--snippets", ALL)
    clone = clone_of(workspace, workspace.parent / "clone")
    library = tmp_path / "no-library" / "snippets"
    monkeypatch.setattr(platform_module, "config_dir", lambda: tmp_path / "no-library")
    monkeypatch.chdir(clone)
    invoke("init", "--yes")
    assert not library.exists() or list(library.iterdir()) == []


def test_a_clone_in_sync_needs_no_confirmation(invoke: Invoke, workspace: Path) -> None:
    """Files already matching the manifest are not a trust boundary crossing."""
    invoke("init", "--mode", "import", "--snippets", ALL)
    result = invoke("init", "--snippets", ALL)
    assert result.code == EXIT_OK
    assert "not composed on this machine" not in result.out


def test_a_fully_scripted_run_never_prompts(invoke: Invoke, workspace: Path) -> None:
    result = invoke(
        "init", "--mode", "import", "--snippets", ALL, "--on-drift", "overwrite", "--yes"
    )
    assert result.code == EXIT_OK


def test_init_output_is_ascii(invoke: Invoke, workspace: Path) -> None:
    assert invoke("init", "--mode", "import", "--snippets", ALL).out.isascii()


def test_init_help_lists_a_flag_for_every_prompt(invoke: Invoke) -> None:
    text = invoke("init", "--help").out
    for flag in ("--mode", "--snippets", "--yes", "--on-drift", "--agents-from"):
        assert flag in text


def test_an_empty_selection_warns_that_the_blocks_will_be_empty(
    invoke: Invoke, workspace: Path
) -> None:
    result = invoke("init", "--mode", "import", "--snippets", "")
    assert result.code == EXIT_OK
    assert "no snippets selected" in result.err


def test_a_non_empty_selection_does_not_warn_about_empty_blocks(
    invoke: Invoke, workspace: Path
) -> None:
    result = invoke("init", "--mode", "import", "--snippets", "overview")
    assert "no snippets selected" not in result.err


def test_init_in_a_directory_with_none_of_its_files_says_so(
    invoke: Invoke, workspace: Path
) -> None:
    result = invoke("init", "--mode", "import", "--snippets", "overview")
    assert result.code == EXIT_OK
    assert "no AGENTS.md, CLAUDE.md, or mdcompose.lock here" in result.err


def test_init_does_not_warn_about_a_bare_directory_once_composed(
    invoke: Invoke, workspace: Path
) -> None:
    invoke("init", "--mode", "import", "--snippets", "overview")
    result = invoke("init", "--mode", "import", "--snippets", "overview")
    assert "no AGENTS.md, CLAUDE.md, or mdcompose.lock here" not in result.err


def test_init_does_not_warn_when_a_managed_file_already_exists(
    invoke: Invoke, workspace: Path
) -> None:
    (workspace / "AGENTS.md").write_text("# Mine\n", encoding="utf-8")
    result = invoke("init", "--mode", "import", "--snippets", "overview")
    assert "no AGENTS.md, CLAUDE.md, or mdcompose.lock here" not in result.err


def test_import_mode_warns_about_a_redundant_hand_written_import(
    invoke: Invoke, workspace: Path
) -> None:
    (workspace / "CLAUDE.md").write_text(
        "@AGENTS.md\n\n# My own Claude notes\n", encoding="utf-8"
    )
    result = invoke("init", "--mode", "import", "--snippets", "overview")
    assert result.code == EXIT_OK
    assert "already has '@AGENTS.md' outside the managed block" in result.err
    assert "# My own Claude notes" in (workspace / "CLAUDE.md").read_text(encoding="utf-8")


def test_import_mode_is_quiet_when_there_is_no_redundant_import(
    invoke: Invoke, workspace: Path
) -> None:
    result = invoke("init", "--mode", "import", "--snippets", "overview")
    assert "outside the managed block" not in result.err


def test_copy_mode_never_warns_about_a_redundant_import(
    invoke: Invoke, workspace: Path
) -> None:
    (workspace / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    result = invoke("init", "--mode", "copy", "--snippets", "overview")
    assert "outside the managed block" not in result.err
