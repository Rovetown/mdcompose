"""The convert command, section 7: the core move between the project pair."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import Invocation

from mdcompose.core import convert_ops, files, managed_block
from mdcompose.core import platform as platform_module
from mdcompose.core.exit_codes import EXIT_ATTENTION, EXIT_OK, AttentionError

Invoke = Callable[..., Invocation]

AGENTS_BLOCK = managed_block.AGENTS_COMPOSITION_BLOCK
CLAUDE_BLOCK = managed_block.CLAUDE_MANAGED_BLOCK

CLAUDE_SOURCE = """\
# Claude notes

Only relevant to Claude Code.

# Shared conventions

Everyone should follow these.
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_directory = tmp_path / "config"
    (config_directory / "snippets").mkdir(parents=True)
    monkeypatch.setattr(platform_module, "config_dir", lambda: config_directory)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return project


def seed_snippet(workspace: Path, name: str = "house") -> None:
    library = workspace.parent / "config" / "snippets"
    (library / f"{name}.md").write_text(
        f"---\ntitle: {name}\n---\n\nHouse rule.\n", encoding="utf-8"
    )


def claude_text(workspace: Path) -> str:
    return (workspace / "CLAUDE.md").read_text(encoding="utf-8")


def agents_text(workspace: Path) -> str:
    return (workspace / "AGENTS.md").read_text(encoding="utf-8")


# 7.4 both directions


def test_claude_to_agents_moves_the_selected_section(invoke: Invoke, workspace: Path) -> None:
    (workspace / "CLAUDE.md").write_text(CLAUDE_SOURCE, encoding="utf-8")
    result = invoke("convert", "CLAUDE.md", "AGENTS.md", "--section", "Shared conventions", "--yes")
    assert result.code == EXIT_OK
    assert "Everyone should follow these." in agents_text(workspace)
    assert "Everyone should follow these." not in claude_text(workspace)
    assert "# Claude notes" in claude_text(workspace)


def test_agents_to_claude_moves_the_selected_section(invoke: Invoke, workspace: Path) -> None:
    (workspace / "AGENTS.md").write_text(
        "# General\n\nfor everyone\n\n# Claude only\n\nnarrow\n", encoding="utf-8"
    )
    result = invoke(
        "convert", "AGENTS.md", "CLAUDE.md", "--section", "Claude only", "--mode", "import", "--yes"
    )
    assert result.code == EXIT_OK
    assert "narrow" in claude_text(workspace)
    assert "narrow" not in agents_text(workspace)


# 7.1 managed block content is not convertible


def test_a_managed_block_section_cannot_be_named_for_conversion(
    invoke: Invoke, workspace: Path
) -> None:
    claude = workspace / "CLAUDE.md"
    claude.write_text(
        managed_block.upsert(CLAUDE_SOURCE, CLAUDE_BLOCK, "## Composed\n\nx\n", claude),
        encoding="utf-8",
    )
    result = invoke("convert", "CLAUDE.md", "AGENTS.md", "--section", "Composed", "--yes")
    assert result.code == EXIT_ATTENTION


def test_unmanaged_sections_convert_while_the_block_stays_in_the_source(
    invoke: Invoke, workspace: Path
) -> None:
    claude = workspace / "CLAUDE.md"
    claude.write_text(
        managed_block.upsert(CLAUDE_SOURCE, CLAUDE_BLOCK, "@AGENTS.md\n", claude),
        encoding="utf-8",
    )
    invoke("convert", "CLAUDE.md", "AGENTS.md", "--section", "Shared conventions", "--yes")
    remaining = claude.read_text(encoding="utf-8")
    assert managed_block.read_blocks(claude).find(CLAUDE_BLOCK) is not None
    assert "Everyone should follow these." not in remaining
    assert "# Claude notes" in remaining


# 7.2 target managed block untouched


def test_the_targets_managed_block_is_byte_identical_afterwards(
    invoke: Invoke, workspace: Path
) -> None:
    (workspace / "CLAUDE.md").write_text(CLAUDE_SOURCE, encoding="utf-8")
    agents = workspace / "AGENTS.md"
    agents.write_text(
        managed_block.upsert("# Existing\n\nkept\n", AGENTS_BLOCK, "composed body\n", agents),
        encoding="utf-8",
    )
    before = managed_block.read_blocks(agents).find(AGENTS_BLOCK)
    invoke("convert", "CLAUDE.md", "AGENTS.md", "--section", "Shared conventions", "--yes")
    after = managed_block.read_blocks(agents).find(AGENTS_BLOCK)
    assert before is not None and after is not None and after.content == before.content


# 7.3 source has no unmanaged content


def test_a_source_that_is_only_a_managed_block_has_nothing_to_convert(
    invoke: Invoke, workspace: Path
) -> None:
    claude = workspace / "CLAUDE.md"
    claude.write_text(
        f"{managed_block.start_marker(CLAUDE_BLOCK)}\n@AGENTS.md\n{managed_block.end_marker(CLAUDE_BLOCK)}\n",
        encoding="utf-8",
    )
    result = invoke("convert", "CLAUDE.md", "AGENTS.md", "--yes")
    assert result.code == EXIT_OK
    assert "nothing to convert" in result.out


# 7.5 error paths


def test_the_same_file_as_source_and_target_is_refused(invoke: Invoke, workspace: Path) -> None:
    (workspace / "AGENTS.md").write_text("# A\n\nx\n", encoding="utf-8")
    result = invoke("convert", "AGENTS.md", "AGENTS.md", "--yes")
    assert result.code == EXIT_ATTENTION
    assert "different" in result.err


def test_a_missing_source_is_refused(invoke: Invoke, workspace: Path) -> None:
    result = invoke("convert", "CLAUDE.md", "AGENTS.md", "--yes")
    assert result.code == EXIT_ATTENTION
    assert "CLAUDE.md" in result.err


def test_an_unsupported_file_is_refused(invoke: Invoke, workspace: Path) -> None:
    (workspace / "NOTES.md").write_text("# N\n\nx\n", encoding="utf-8")
    result = invoke("convert", "NOTES.md", "AGENTS.md", "--yes")
    assert result.code == EXIT_ATTENTION
    assert "AGENTS.md and CLAUDE.md" in result.err


# 7.6 manifest hash unaffected


def test_doctor_reports_clean_after_a_conversion(invoke: Invoke, workspace: Path) -> None:
    seed_snippet(workspace)
    (workspace / "CLAUDE.md").write_text(CLAUDE_SOURCE, encoding="utf-8")
    invoke("init", "--mode", "copy", "--snippets", "house")
    invoke("convert", "CLAUDE.md", "AGENTS.md", "--section", "Shared conventions", "--yes")
    result = invoke("doctor")
    assert result.code == EXIT_OK
    assert "drifted" not in result.out


# confirmation gate


def test_convert_without_yes_and_no_terminal_is_refused(invoke: Invoke, workspace: Path) -> None:
    (workspace / "CLAUDE.md").write_text(CLAUDE_SOURCE, encoding="utf-8")
    result = invoke("convert", "CLAUDE.md", "AGENTS.md", "--section", "Shared conventions")
    assert result.code == EXIT_ATTENTION
    assert "--yes" in result.err
    assert not (workspace / "AGENTS.md").exists()


# 8.1 the diff covers both files


def test_the_diff_shows_removal_from_source_and_addition_to_target(
    invoke: Invoke, workspace: Path
) -> None:
    (workspace / "CLAUDE.md").write_text(CLAUDE_SOURCE, encoding="utf-8")
    result = invoke(
        "convert", "CLAUDE.md", "AGENTS.md", "--section", "Shared conventions", "--yes"
    )
    lines = result.out.splitlines()
    assert any(line.startswith("-") and "Everyone should follow these." in line for line in lines)
    assert any(line.startswith("+") and "Everyone should follow these." in line for line in lines)
    assert "CLAUDE.md" in result.out and "AGENTS.md" in result.out


# 8.2 confirmation required; decline leaves both files unchanged


def test_declining_after_the_diff_writes_nothing(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mdcompose.commands import convert_cmd

    claude = workspace / "CLAUDE.md"
    claude.write_text(CLAUDE_SOURCE, encoding="utf-8")
    before = claude.read_bytes()
    monkeypatch.setattr(convert_cmd, "is_interactive", lambda: True)
    monkeypatch.setattr("typer.confirm", lambda *_a, **_k: False)
    result = invoke("convert", "CLAUDE.md", "AGENTS.md", "--section", "Shared conventions")
    assert result.code == EXIT_OK
    assert claude.read_bytes() == before
    assert not (workspace / "AGENTS.md").exists()
    assert "Everyone should follow these." in result.out  # the diff was still shown


# 8.3 the flag prints the diff but skips the prompt


def test_the_yes_flag_prints_the_diff_and_proceeds(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import typer

    def refuse(*_a: object, **_k: object) -> bool:
        raise AssertionError("prompt should not be reached with --yes")

    monkeypatch.setattr(typer, "confirm", refuse)
    (workspace / "CLAUDE.md").write_text(CLAUDE_SOURCE, encoding="utf-8")
    result = invoke(
        "convert", "CLAUDE.md", "AGENTS.md", "--section", "Shared conventions", "--yes"
    )
    assert result.code == EXIT_OK
    assert "@@" in result.out  # a unified-diff hunk header
    assert "Everyone should follow these." in agents_text(workspace)


# 8.4 / 8.5 selection via the picker


def test_the_picker_selection_is_converted(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mdcompose.commands import convert_cmd

    (workspace / "CLAUDE.md").write_text(CLAUDE_SOURCE, encoding="utf-8")

    def pick_shared(_output: object):  # noqa: ANN202
        return lambda available: tuple(s for s in available if s.heading == "Shared conventions")

    monkeypatch.setattr(convert_cmd, "_section_picker", pick_shared)
    result = invoke("convert", "CLAUDE.md", "AGENTS.md", "--yes")
    assert result.code == EXIT_OK
    assert "Everyone should follow these." in agents_text(workspace)


def test_selecting_no_sections_in_the_picker_writes_nothing(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mdcompose.commands import convert_cmd

    claude = workspace / "CLAUDE.md"
    claude.write_text(CLAUDE_SOURCE, encoding="utf-8")
    before = claude.read_bytes()
    monkeypatch.setattr(convert_cmd, "_section_picker", lambda _output: (lambda _available: ()))
    result = invoke("convert", "CLAUDE.md", "AGENTS.md")
    assert result.code == EXIT_OK
    assert claude.read_bytes() == before
    assert not (workspace / "AGENTS.md").exists()


# 9.1 target write ordered first


def test_a_failed_target_write_leaves_the_source_untouched(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude = workspace / "CLAUDE.md"
    claude.write_text(CLAUDE_SOURCE, encoding="utf-8")
    before = claude.read_bytes()
    real = files.write_text

    def fail_on_target(path: Path, text: str, **kw: object) -> None:
        if path.name == "AGENTS.md":
            raise AttentionError("simulated target write failure")
        real(path, text, **kw)

    monkeypatch.setattr(convert_ops.files, "write_text", fail_on_target)
    result = invoke(
        "convert", "CLAUDE.md", "AGENTS.md", "--section", "Shared conventions", "--yes"
    )
    assert result.code == EXIT_ATTENTION
    assert claude.read_bytes() == before


# 9.2 only the converted sections leave the source


def test_unconverted_sections_stay_in_the_source_unchanged(
    invoke: Invoke, workspace: Path
) -> None:
    claude = workspace / "CLAUDE.md"
    claude.write_text(
        "# Keep one\n\nfirst kept\n\n# Move me\n\ngoing\n\n# Keep two\n\nsecond kept\n",
        encoding="utf-8",
    )
    invoke("convert", "CLAUDE.md", "AGENTS.md", "--section", "Move me", "--yes")
    remaining = claude_text(workspace)
    assert "first kept" in remaining
    assert "second kept" in remaining
    assert "going" not in remaining
    assert "# Keep one" in remaining and "# Keep two" in remaining


# 9.3 a source left with only a managed block is kept


def test_a_source_reduced_to_its_block_is_not_deleted(invoke: Invoke, workspace: Path) -> None:
    claude = workspace / "CLAUDE.md"
    claude.write_text(
        managed_block.upsert(
            "# Only section\n\nmove this out\n", CLAUDE_BLOCK, "@AGENTS.md\n", claude
        ),
        encoding="utf-8",
    )
    invoke("convert", "CLAUDE.md", "AGENTS.md", "--section", "Only section", "--yes")
    assert claude.exists()
    assert managed_block.read_blocks(claude).find(CLAUDE_BLOCK) is not None
    assert "move this out" not in claude_text(workspace)


# 9.4 converted content lands outside the target's block


def test_converted_content_is_written_outside_the_target_block(
    invoke: Invoke, workspace: Path
) -> None:
    (workspace / "CLAUDE.md").write_text(CLAUDE_SOURCE, encoding="utf-8")
    agents = workspace / "AGENTS.md"
    agents.write_text(
        managed_block.upsert("# Head\n\nx\n", AGENTS_BLOCK, "composed\n", agents), encoding="utf-8"
    )
    invoke("convert", "CLAUDE.md", "AGENTS.md", "--section", "Shared conventions", "--yes")
    text = agents_text(workspace)
    end = text.index(managed_block.end_marker(AGENTS_BLOCK))
    assert end < text.index("Everyone should follow these.")


# 9.5 converted content survives init and adds no snippet id


def test_converted_content_survives_init_and_adds_no_snippet(
    invoke: Invoke, workspace: Path
) -> None:
    from mdcompose.core import manifest as manifest_module

    seed_snippet(workspace)
    (workspace / "CLAUDE.md").write_text(CLAUDE_SOURCE, encoding="utf-8")
    invoke("init", "--mode", "copy", "--snippets", "house")
    invoke("convert", "CLAUDE.md", "AGENTS.md", "--section", "Shared conventions", "--yes")
    invoke("init", "--mode", "copy", "--snippets", "house")
    assert "Everyone should follow these." in agents_text(workspace)
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(workspace))
    assert manifest is not None
    assert [entry.id for entry in manifest.snippets_in_order()] == ["house"]


# 10. --mode when creating a CLAUDE.md managed block

AGENTS_TWO = "# General\n\nfor all\n\n# Narrow\n\nclaude only\n"


def test_mode_import_creates_the_block_with_an_import_directive(
    invoke: Invoke, workspace: Path
) -> None:
    from mdcompose.core import manifest as manifest_module

    (workspace / "AGENTS.md").write_text(AGENTS_TWO, encoding="utf-8")
    result = invoke(
        "convert", "AGENTS.md", "CLAUDE.md", "--section", "Narrow", "--mode", "import", "--yes"
    )
    assert result.code == EXIT_OK
    block = managed_block.read_blocks(workspace / "CLAUDE.md").find(CLAUDE_BLOCK)
    assert block is not None and block.content.strip() == "@AGENTS.md"
    assert "claude only" in claude_text(workspace)
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(workspace))
    assert manifest is not None
    assert manifest.files["claude_md"].mode == "import"


def test_mode_copy_creates_an_empty_block_and_records_the_mode(
    invoke: Invoke, workspace: Path
) -> None:
    from mdcompose.core import manifest as manifest_module

    (workspace / "AGENTS.md").write_text(AGENTS_TWO, encoding="utf-8")
    result = invoke(
        "convert", "AGENTS.md", "CLAUDE.md", "--section", "Narrow", "--mode", "copy", "--yes"
    )
    assert result.code == EXIT_OK
    block = managed_block.read_blocks(workspace / "CLAUDE.md").find(CLAUDE_BLOCK)
    assert block is not None and block.content.strip() == ""
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(workspace))
    assert manifest is not None and manifest.files["claude_md"].mode == "copy"


def test_no_mode_falls_back_to_the_recorded_project_mode(
    invoke: Invoke, workspace: Path
) -> None:
    (workspace / "AGENTS.md").write_text(AGENTS_TWO, encoding="utf-8")
    (workspace / "mdcompose.lock").write_text(
        '{\n  "schema_version": 1,\n  "generated_by": "mdcompose test",\n'
        '  "generated_at": "2026-01-01T00:00:00+00:00",\n  "detected_stack": [],\n'
        '  "snippets": [],\n  "files": {\n    "claude_md": {\n      "path": "CLAUDE.md",\n'
        '      "mode": "copy",\n      "managed_block_hash": "0"\n    }\n  }\n}\n',
        encoding="utf-8",
    )
    result = invoke("convert", "AGENTS.md", "CLAUDE.md", "--section", "Narrow", "--yes")
    assert result.code == EXIT_OK
    block = managed_block.read_blocks(workspace / "CLAUDE.md").find(CLAUDE_BLOCK)
    assert block is not None and block.content.strip() == ""  # copy mode -> empty block


def test_no_mode_and_none_recorded_and_no_terminal_is_refused(
    invoke: Invoke, workspace: Path
) -> None:
    (workspace / "AGENTS.md").write_text(AGENTS_TWO, encoding="utf-8")
    result = invoke("convert", "AGENTS.md", "CLAUDE.md", "--section", "Narrow", "--yes")
    assert result.code == EXIT_ATTENTION
    assert "--mode" in result.err


def test_no_mode_asks_when_there_is_a_terminal(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mdcompose.commands import convert_cmd

    (workspace / "AGENTS.md").write_text(AGENTS_TWO, encoding="utf-8")
    monkeypatch.setattr(convert_cmd, "is_interactive", lambda: True)
    monkeypatch.setattr(convert_cmd, "prompt_choice", lambda *_a, **_k: "import")
    result = invoke("convert", "AGENTS.md", "CLAUDE.md", "--section", "Narrow", "--yes")
    assert result.code == EXIT_OK
    block = managed_block.read_blocks(workspace / "CLAUDE.md").find(CLAUDE_BLOCK)
    assert block is not None and block.content.strip() == "@AGENTS.md"


# 10.3 / 10.4 rejection


def test_mode_is_rejected_when_claude_already_has_a_block(
    invoke: Invoke, workspace: Path
) -> None:
    claude = workspace / "CLAUDE.md"
    claude.write_text(
        managed_block.upsert("# Mine\n\nx\n", CLAUDE_BLOCK, "@AGENTS.md\n", claude),
        encoding="utf-8",
    )
    (workspace / "AGENTS.md").write_text(AGENTS_TWO, encoding="utf-8")
    result = invoke(
        "convert", "AGENTS.md", "CLAUDE.md", "--section", "Narrow", "--mode", "copy", "--yes"
    )
    assert result.code == EXIT_ATTENTION
    assert "init" in result.err


def test_mode_is_rejected_when_the_target_is_agents_md(invoke: Invoke, workspace: Path) -> None:
    (workspace / "CLAUDE.md").write_text(CLAUDE_SOURCE, encoding="utf-8")
    result = invoke(
        "convert", "CLAUDE.md", "AGENTS.md", "--section", "Shared conventions", "--mode", "import",
        "--yes",
    )
    assert result.code == EXIT_ATTENTION
    assert "AGENTS.md" in result.err
