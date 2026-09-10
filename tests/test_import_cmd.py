"""The import command, section 2: reading and validating the source file."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import Invocation

from mdcompose.core import files, managed_block, snippets
from mdcompose.core import platform as platform_module
from mdcompose.core.exit_codes import EXIT_ATTENTION, EXIT_OK
from mdcompose.core.platform import PlatformInfo, ResolvedPath

CLAUDE_BLOCK = managed_block.CLAUDE_MANAGED_BLOCK


def with_block(before: str, block_body: str, after: str) -> str:
    return (
        f"{before}"
        f"{managed_block.start_marker(CLAUDE_BLOCK)}\n"
        f"{block_body}\n"
        f"{managed_block.end_marker(CLAUDE_BLOCK)}\n"
        f"{after}"
    )

Invoke = Callable[..., Invocation]

SOURCE = """\
Preamble line.

# Conventions

House style.

## Testing

Run pytest before every commit.

# Deployment

Ship on green.
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated project directory and config, with a source file alongside."""
    config_directory = tmp_path / "config"
    (config_directory / "snippets").mkdir(parents=True)
    monkeypatch.setattr(platform_module, "config_dir", lambda: config_directory)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "CLAUDE.md").write_text(SOURCE, encoding="utf-8")
    return project


def source_path(workspace: Path) -> Path:
    return workspace.parent / "elsewhere" / "CLAUDE.md"


def seed_snippet(workspace: Path, name: str = "house", body: str = "House rule.\n") -> None:
    library = workspace.parent / "config" / "snippets"
    (library / f"{name}.md").write_text(f"---\ntitle: {name}\n---\n\n{body}", encoding="utf-8")


# 2.1 reading a source from any path


def test_a_source_outside_the_project_is_read_and_its_sections_are_importable(
    invoke: Invoke, workspace: Path
) -> None:
    result = invoke("import", str(source_path(workspace)), "--section", "Conventions")
    assert result.code == EXIT_OK
    assert "House style." in (workspace / "AGENTS.md").read_text(encoding="utf-8")


# 2.2 error paths


def test_a_missing_source_is_reported_and_exits_one(invoke: Invoke, workspace: Path) -> None:
    result = invoke("import", str(workspace.parent / "nope.md"))
    assert result.code == EXIT_ATTENTION
    assert "nope.md" in result.err


def test_a_directory_source_is_reported_and_exits_one(invoke: Invoke, workspace: Path) -> None:
    result = invoke("import", str(workspace.parent / "elsewhere"))
    assert result.code == EXIT_ATTENTION
    assert "elsewhere" in result.err
    assert "directory" in result.err


def test_an_unreadable_source_is_reported_and_exits_one(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mdcompose.core.exit_codes import AttentionError

    def deny(path: Path) -> str:
        raise AttentionError(f"{path}: cannot be read (Permission denied)")

    monkeypatch.setattr(files, "read_text", deny)
    result = invoke("import", str(source_path(workspace)))
    assert result.code == EXIT_ATTENTION
    assert "Permission denied" in result.err


# 2.3 source is also the target


def test_importing_a_file_into_itself_is_refused(invoke: Invoke, workspace: Path) -> None:
    (workspace / "AGENTS.md").write_text(SOURCE, encoding="utf-8")
    result = invoke("import", str(workspace / "AGENTS.md"))
    assert result.code == EXIT_ATTENTION
    assert "itself" in result.err


def test_a_relative_source_that_resolves_to_the_target_is_refused(
    invoke: Invoke, workspace: Path
) -> None:
    (workspace / "AGENTS.md").write_text(SOURCE, encoding="utf-8")
    result = invoke("import", "AGENTS.md")
    assert result.code == EXIT_ATTENTION
    assert "itself" in result.err


# 2.4 WSL boundary warning


def test_a_source_on_a_windows_mount_warns_and_continues(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = source_path(workspace)

    def on_mount(raw: object, info: PlatformInfo) -> ResolvedPath:
        return ResolvedPath(path=real, exists=True, on_windows_mount=True)

    monkeypatch.setattr(platform_module, "resolve_path", on_mount)
    result = invoke("import", str(real), "--section", "Conventions")
    assert result.code == EXIT_OK
    assert "/mnt/" in result.err
    assert "House style." in (workspace / "AGENTS.md").read_text(encoding="utf-8")


# 2.5 source is never modified


def test_the_source_is_byte_identical_after_a_successful_import(
    invoke: Invoke, workspace: Path
) -> None:
    before = source_path(workspace).read_bytes()
    result = invoke("import", str(source_path(workspace)), "--section", "Conventions")
    assert result.code == EXIT_OK
    assert source_path(workspace).read_bytes() == before


def test_the_source_is_byte_identical_after_a_failed_import(
    invoke: Invoke, workspace: Path
) -> None:
    before = source_path(workspace).read_bytes()
    result = invoke("import", str(source_path(workspace)), "--section", "Not a heading here")
    assert result.code == EXIT_ATTENTION
    assert source_path(workspace).read_bytes() == before


# 1.11 keyword no-match and keyword-unused reporting


def test_a_keyword_matching_nothing_reports_and_exits_zero(
    invoke: Invoke, workspace: Path
) -> None:
    result = invoke("import", str(source_path(workspace)), "--keyword", "kubernetes")
    assert result.code == EXIT_OK
    assert "no section matched" in result.out


def test_a_keyword_alongside_named_sections_is_reported_as_unused(
    invoke: Invoke, workspace: Path
) -> None:
    result = invoke(
        "import",
        str(source_path(workspace)),
        "--section",
        "Deployment",
        "--keyword",
        "kubernetes",
    )
    assert result.code == EXIT_OK
    assert "Ship on green." in (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert "keyword" in result.err.lower()


def test_a_named_section_absent_from_the_source_exits_one(
    invoke: Invoke, workspace: Path
) -> None:
    result = invoke("import", str(source_path(workspace)), "--section", "Nonexistent")
    assert result.code == EXIT_ATTENTION
    assert "Nonexistent" in result.err


# 3.1 / 3.2 managed block exclusion


def test_managed_block_content_cannot_be_named_for_import(
    invoke: Invoke, workspace: Path
) -> None:
    source = source_path(workspace)
    source.write_text(
        with_block(
            "# Mine\n\nkeep this\n\n",
            "## Composed thing\n\nfrom a snippet",
            "\n# Later\n\ntail\n",
        ),
        encoding="utf-8",
    )
    result = invoke("import", str(source), "--section", "Composed thing")
    assert result.code == EXIT_ATTENTION
    assert "Composed thing" in result.err


def test_sections_around_a_managed_block_are_both_importable(
    invoke: Invoke, workspace: Path
) -> None:
    source = source_path(workspace)
    source.write_text(
        with_block("# Before\n\nb\n\n", "## Composed\n\nx", "\n# After\n\na\n"),
        encoding="utf-8",
    )
    result = invoke("import", str(source), "--section", "Before", "--section", "After")
    assert result.code == EXIT_OK
    text = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert "# Before" in text and "# After" in text
    assert "## Composed" not in text


# 3.3 source is entirely a managed block


def test_a_source_that_is_only_a_managed_block_has_nothing_to_import(
    invoke: Invoke, workspace: Path
) -> None:
    source = source_path(workspace)
    source.write_text(with_block("", "## Composed\n\nonly this", ""), encoding="utf-8")
    result = invoke("import", str(source))
    assert result.code == EXIT_ATTENTION
    assert "nothing to import" in result.err


# 3.4 malformed markers


def test_a_source_with_malformed_markers_is_refused_and_writes_nothing(
    invoke: Invoke, workspace: Path
) -> None:
    source = source_path(workspace)
    source.write_text(
        f"# Real\n\nbody\n\n{managed_block.start_marker(CLAUDE_BLOCK)}\nunclosed\n",
        encoding="utf-8",
    )
    result = invoke("import", str(source))
    assert result.code == EXIT_ATTENTION
    assert not (workspace / "AGENTS.md").exists()


# 4.2 multiple sections in source order


def test_multiple_named_sections_are_applied_in_source_order(
    invoke: Invoke, workspace: Path
) -> None:
    result = invoke(
        "import", str(source_path(workspace)), "--section", "Deployment", "--section", "Conventions"
    )
    assert result.code == EXIT_OK
    text = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert text.index("# Conventions") < text.index("# Deployment")


# 4.5 target selection


def test_the_default_target_is_agents_md(invoke: Invoke, workspace: Path) -> None:
    invoke("import", str(source_path(workspace)), "--section", "Deployment")
    assert (workspace / "AGENTS.md").exists()
    assert not (workspace / "CLAUDE.md").exists()


def test_the_claude_target_flag_writes_claude_md(invoke: Invoke, workspace: Path) -> None:
    invoke("import", str(source_path(workspace)), "--section", "Deployment", "--to-claude")
    assert (workspace / "CLAUDE.md").exists()
    assert not (workspace / "AGENTS.md").exists()


# 4.6 content lands outside an existing managed block


def test_import_leaves_an_existing_managed_block_byte_identical(
    invoke: Invoke, workspace: Path
) -> None:
    agents = workspace / "AGENTS.md"
    block_id = managed_block.AGENTS_COMPOSITION_BLOCK
    agents.write_text(
        managed_block.upsert("# Mine\n\nkept\n", block_id, "composed line\n", agents),
        encoding="utf-8",
    )
    before = managed_block.read_blocks(agents).find(block_id)
    invoke("import", str(source_path(workspace)), "--section", "Deployment")
    after = managed_block.read_blocks(agents).find(block_id)
    assert after is not None and before is not None and after.content == before.content
    assert "Ship on green." in agents.read_text(encoding="utf-8")


# 4.7 target created when absent


def test_import_creates_a_missing_target_with_no_managed_block(
    invoke: Invoke, workspace: Path
) -> None:
    invoke("import", str(source_path(workspace)), "--section", "Deployment")
    text = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert "Ship on green." in text
    assert managed_block.read_blocks(workspace / "AGENTS.md").blocks == ()


# 4.8 imported content survives a later init


def test_imported_content_survives_a_later_init(invoke: Invoke, workspace: Path) -> None:
    seed_snippet(workspace)
    invoke("import", str(source_path(workspace)), "--section", "Deployment")
    result = invoke("init", "--mode", "copy", "--snippets", "house")
    assert result.code == EXIT_OK
    text = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert "Ship on green." in text
    assert "House rule." in text


# 4.9 manifest hash unaffected


def test_doctor_reports_clean_after_an_import(invoke: Invoke, workspace: Path) -> None:
    seed_snippet(workspace)
    invoke("init", "--mode", "copy", "--snippets", "house")
    invoke("import", str(source_path(workspace)), "--section", "Deployment")
    result = invoke("doctor")
    assert result.code == EXIT_OK
    assert "drifted" not in result.out


# 4.4 nothing selected leaves files untouched (non-interactive path refuses instead)


def test_import_without_a_section_and_no_terminal_is_refused(
    invoke: Invoke, workspace: Path
) -> None:
    result = invoke("import", str(source_path(workspace)))
    assert result.code == EXIT_ATTENTION
    assert "--section" in result.err
    assert not (workspace / "AGENTS.md").exists()


def test_picking_nothing_in_the_picker_leaves_files_untouched(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mdcompose.commands import import_cmd

    monkeypatch.setattr(import_cmd, "_picker", lambda _output: (lambda _available: ()))
    result = invoke("import", str(source_path(workspace)))
    assert result.code == EXIT_OK
    assert not (workspace / "AGENTS.md").exists()


# 5. save as snippet


def library_dir(workspace: Path) -> Path:
    return workspace.parent / "config" / "snippets"


def library_body(workspace: Path, name: str = "testing") -> str:
    return (library_dir(workspace) / f"{name}.md").read_text(encoding="utf-8")


def agents_text(workspace: Path) -> str:
    return (workspace / "AGENTS.md").read_text(encoding="utf-8")


def save_testing(invoke: Invoke, workspace: Path, name: str = "testing", *extra: str) -> Invocation:
    return invoke(
        "import",
        str(source_path(workspace)),
        "--section",
        "Testing",
        "--save-as-snippet",
        name,
        *extra,
    )


def test_save_as_snippet_writes_the_content_to_the_library(
    invoke: Invoke, workspace: Path
) -> None:
    result = save_testing(invoke, workspace)
    assert result.code == EXIT_OK
    saved = (library_dir(workspace) / "testing.md").read_text(encoding="utf-8")
    assert "Run pytest before every commit." in saved


def test_save_as_snippet_populates_frontmatter_from_flags(
    invoke: Invoke, workspace: Path
) -> None:
    save_testing(invoke, workspace, "testing", "--category", "quality", "--tags", "python, ci")
    snippet = snippets.read(library_dir(workspace) / "testing.md")
    assert snippet.title == "Testing"
    assert snippet.category == "quality"
    assert snippet.tags == ("python", "ci")
    assert snippet.source_heading == "Testing"
    assert snippet.source_path.endswith("CLAUDE.md")


def test_save_as_snippet_still_applies_to_the_project(invoke: Invoke, workspace: Path) -> None:
    save_testing(invoke, workspace)
    assert (library_dir(workspace) / "testing.md").exists()
    agents = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert "Run pytest before every commit." in agents


def test_save_as_snippet_concatenates_multiple_sections_in_source_order(
    invoke: Invoke, workspace: Path
) -> None:
    invoke(
        "import",
        str(source_path(workspace)),
        "--section",
        "Deployment",
        "--section",
        "Conventions",
        "--save-as-snippet",
        "combined",
    )
    body = snippets.read(library_dir(workspace) / "combined.md").body
    assert body.index("House style.") < body.index("Ship on green.")


def test_save_as_snippet_rejects_an_unusable_name(invoke: Invoke, workspace: Path) -> None:
    result = save_testing(invoke, workspace, "bad/name")
    assert result.code == EXIT_ATTENTION
    assert not (workspace / "AGENTS.md").exists()


def test_provenance_does_not_reach_a_composed_block(invoke: Invoke, workspace: Path) -> None:
    save_testing(invoke, workspace)
    result = invoke("init", "--mode", "copy", "--snippets", "testing")
    assert result.code == EXIT_OK
    block = managed_block.read_blocks(workspace / "AGENTS.md").find(
        managed_block.AGENTS_COMPOSITION_BLOCK
    )
    assert block is not None
    assert "source_path" not in block.content
    assert "imported_at" not in block.content
    assert "Run pytest before every commit." in block.content


def test_a_saved_snippet_is_immediately_usable(invoke: Invoke, workspace: Path) -> None:
    save_testing(invoke, workspace)
    listed = invoke("snippet", "list")
    assert "testing" in listed.out
    composed = invoke("init", "--mode", "copy", "--snippets", "testing")
    assert composed.code == EXIT_OK


# 6. snippet collision handling


def divergent_library_snippet(workspace: Path, body: str = "A different rule.\n") -> None:
    (library_dir(workspace) / "testing.md").write_text(
        f"---\ntitle: testing\n---\n\n{body}", encoding="utf-8"
    )


# 6.1 identical content is a no-op


def test_saving_identical_content_rewrites_nothing(invoke: Invoke, workspace: Path) -> None:
    save_testing(invoke, workspace)
    before = (library_dir(workspace) / "testing.md").read_bytes()
    result = save_testing(invoke, workspace)
    assert result.code == EXIT_OK
    assert "already in the library" in result.out
    assert (library_dir(workspace) / "testing.md").read_bytes() == before


def test_a_line_ending_only_difference_counts_as_identical(
    invoke: Invoke, workspace: Path
) -> None:
    save_testing(invoke, workspace)
    path = library_dir(workspace) / "testing.md"
    path.write_bytes(path.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
    result = save_testing(invoke, workspace)
    assert result.code == EXIT_OK
    assert "already in the library" in result.out


# 6.2 differing content, per resolution


def test_collision_overwrite_replaces_the_library_copy(invoke: Invoke, workspace: Path) -> None:
    save_testing(invoke, workspace)
    divergent_library_snippet(workspace)
    result = save_testing(invoke, workspace, "testing", "--on-collision", "overwrite")
    assert result.code == EXIT_OK
    assert "Run pytest before every commit." in library_body(workspace)


def test_collision_keep_leaves_the_library_copy(invoke: Invoke, workspace: Path) -> None:
    save_testing(invoke, workspace)
    divergent_library_snippet(workspace)
    result = save_testing(invoke, workspace, "testing", "--on-collision", "keep")
    assert result.code == EXIT_OK
    assert "A different rule." in library_body(workspace)


def test_collision_rename_saves_under_a_new_name(
    invoke: Invoke, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mdcompose.commands import import_cmd

    save_testing(invoke, workspace)
    divergent_library_snippet(workspace)
    monkeypatch.setattr(import_cmd, "_ask_new_name", lambda _output, _library: "testing-v2")
    result = save_testing(invoke, workspace, "testing", "--on-collision", "rename")
    assert result.code == EXIT_OK
    assert (library_dir(workspace) / "testing-v2.md").exists()
    assert "A different rule." in library_body(workspace)


# 6.3 keep still applies to the project


def test_collision_keep_still_applies_to_the_target(invoke: Invoke, workspace: Path) -> None:
    save_testing(invoke, workspace)
    (workspace / "AGENTS.md").unlink()
    divergent_library_snippet(workspace)
    save_testing(invoke, workspace, "testing", "--on-collision", "keep")
    assert "Run pytest before every commit." in agents_text(workspace)


# 6.4 the flag skips the prompt


def test_the_collision_flag_applies_without_a_prompt(invoke: Invoke, workspace: Path) -> None:
    save_testing(invoke, workspace)
    divergent_library_snippet(workspace)
    result = save_testing(invoke, workspace, "testing", "--on-collision", "overwrite")
    assert result.code == EXIT_OK
    assert "already exists" not in result.err


def test_a_collision_without_a_flag_or_terminal_is_refused(
    invoke: Invoke, workspace: Path
) -> None:
    save_testing(invoke, workspace)
    divergent_library_snippet(workspace)
    result = save_testing(invoke, workspace)
    assert result.code == EXIT_ATTENTION
    assert "--on-collision" in result.err


def test_rename_without_a_terminal_is_refused(invoke: Invoke, workspace: Path) -> None:
    save_testing(invoke, workspace)
    divergent_library_snippet(workspace)
    result = save_testing(invoke, workspace, "testing", "--on-collision", "rename")
    assert result.code == EXIT_ATTENTION
    assert "terminal" in result.err


def test_an_invalid_collision_choice_is_refused(invoke: Invoke, workspace: Path) -> None:
    save_testing(invoke, workspace)
    divergent_library_snippet(workspace)
    result = save_testing(invoke, workspace, "testing", "--on-collision", "sideways")
    assert result.code == EXIT_ATTENTION
    assert "overwrite" in result.err
