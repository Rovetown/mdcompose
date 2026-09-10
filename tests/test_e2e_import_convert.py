"""End-to-end checks for import and convert working with init and the library."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import Invocation

from mdcompose.core import managed_block
from mdcompose.core import manifest as manifest_module
from mdcompose.core import platform as platform_module
from mdcompose.core.exit_codes import EXIT_OK

Invoke = Callable[..., Invocation]

AGENTS_BLOCK = managed_block.AGENTS_COMPOSITION_BLOCK
CLAUDE_BLOCK = managed_block.CLAUDE_MANAGED_BLOCK

FOREIGN_CLAUDE = """\
# Testing discipline

Run the suite before every commit.

# Review checklist

Check the diff against the spec.

# Claude-only quirks

Notes that only matter inside Claude Code.
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_directory = tmp_path / "config"
    (config_directory / "snippets").mkdir(parents=True)
    monkeypatch.setattr(platform_module, "config_dir", lambda: config_directory)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    foreign = tmp_path / "other-project"
    foreign.mkdir()
    (foreign / "CLAUDE.md").write_text(FOREIGN_CLAUDE, encoding="utf-8")
    return project


def foreign_claude(workspace: Path) -> str:
    return str(workspace.parent / "other-project" / "CLAUDE.md")


def library(workspace: Path) -> Path:
    return workspace.parent / "config" / "snippets"


def seed(workspace: Path, name: str = "base") -> None:
    (library(workspace) / f"{name}.md").write_text(
        f"---\ntitle: {name}\n---\n\nBase rule.\n", encoding="utf-8"
    )


def agents(workspace: Path) -> str:
    return (workspace / "AGENTS.md").read_text(encoding="utf-8")


# 11.0 cold start: an empty library gets its first snippet from import


def test_cold_start_import_save_as_snippet_then_list_and_compose(
    invoke: Invoke, workspace: Path
) -> None:
    assert list(library(workspace).iterdir()) == []
    imported = invoke(
        "import", foreign_claude(workspace), "--section", "Testing discipline",
        "--save-as-snippet", "testing",
    )
    assert imported.code == EXIT_OK
    assert "testing" in invoke("snippet", "list").out
    composed = invoke("init", "--mode", "copy", "--snippets", "testing")
    assert composed.code == EXIT_OK
    block = managed_block.read_blocks(workspace / "AGENTS.md").find(AGENTS_BLOCK)
    assert block is not None and "Run the suite before every commit." in block.content


# 11.1 import from an unrelated project, then init, content stays put


def test_two_imported_sections_survive_a_later_init(invoke: Invoke, workspace: Path) -> None:
    seed(workspace)
    invoke(
        "import", foreign_claude(workspace),
        "--section", "Testing discipline", "--section", "Review checklist",
    )
    invoke("init", "--mode", "copy", "--snippets", "base")
    text = agents(workspace)
    assert "Run the suite before every commit." in text
    assert "Check the diff against the spec." in text
    assert "Base rule." in text


# 11.2 the snippet composes into the block while the paste stays outside it


def test_a_saved_import_is_both_composed_and_left_as_a_paste(
    invoke: Invoke, workspace: Path
) -> None:
    invoke(
        "import", foreign_claude(workspace), "--section", "Review checklist",
        "--save-as-snippet", "review",
    )
    invoke("init", "--mode", "copy", "--snippets", "review")
    text = agents(workspace)
    block = managed_block.read_blocks(workspace / "AGENTS.md").find(AGENTS_BLOCK)
    assert block is not None
    assert "Check the diff against the spec." in block.content
    outside = text.replace(block.content, "", 1)
    assert "Check the diff against the spec." in outside  # the one-off paste remains


# 11.3 convert leaves both managed blocks intact


def test_convert_moves_a_section_and_leaves_both_blocks_intact(
    invoke: Invoke, workspace: Path
) -> None:
    seed(workspace)
    (workspace / "CLAUDE.md").write_text(FOREIGN_CLAUDE, encoding="utf-8")
    invoke("init", "--mode", "copy", "--snippets", "base")
    claude_before = managed_block.read_blocks(workspace / "CLAUDE.md").find(CLAUDE_BLOCK)
    agents_before = managed_block.read_blocks(workspace / "AGENTS.md").find(AGENTS_BLOCK)

    result = invoke(
        "convert", "CLAUDE.md", "AGENTS.md", "--section", "Claude-only quirks", "--yes"
    )
    assert result.code == EXIT_OK

    claude_after = managed_block.read_blocks(workspace / "CLAUDE.md").find(CLAUDE_BLOCK)
    agents_after = managed_block.read_blocks(workspace / "AGENTS.md").find(AGENTS_BLOCK)
    assert claude_before is not None and claude_after is not None
    assert claude_after.content == claude_before.content
    assert agents_before is not None and agents_after is not None
    assert agents_after.content == agents_before.content
    assert "Notes that only matter inside Claude Code." not in (
        workspace / "CLAUDE.md"
    ).read_text(encoding="utf-8")
    assert "Notes that only matter inside Claude Code." in agents(workspace)


# 11.4 fully non-interactive


def test_import_and_convert_run_non_interactively_with_no_prompt(
    invoke: Invoke, workspace: Path
) -> None:
    (workspace / "CLAUDE.md").write_text(FOREIGN_CLAUDE, encoding="utf-8")
    imported = invoke("import", foreign_claude(workspace), "--section", "Review checklist")
    assert imported.code == EXIT_OK
    converted = invoke(
        "convert", "CLAUDE.md", "AGENTS.md", "--section", "Claude-only quirks", "--yes"
    )
    assert converted.code == EXIT_OK


# 11.5 doctor clean after both


def test_doctor_is_clean_after_an_import_and_after_a_conversion(
    invoke: Invoke, workspace: Path
) -> None:
    seed(workspace)
    (workspace / "CLAUDE.md").write_text(FOREIGN_CLAUDE, encoding="utf-8")
    invoke("init", "--mode", "copy", "--snippets", "base")
    invoke("import", foreign_claude(workspace), "--section", "Testing discipline")
    assert "drifted" not in invoke("doctor").out
    invoke("convert", "CLAUDE.md", "AGENTS.md", "--section", "Claude-only quirks", "--yes")
    after = invoke("doctor")
    assert after.code == EXIT_OK
    assert "drifted" not in after.out
    assert manifest_module.load_manifest(manifest_module.manifest_path(workspace)) is not None
