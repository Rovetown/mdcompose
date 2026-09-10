"""The snippet commands: list, edit, remove, adopt."""

from __future__ import annotations

import json
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import Invocation

from mdcompose.core import files
from mdcompose.core import manifest as manifest_module
from mdcompose.core import platform as platform_module
from mdcompose.core import snippets as snippets_module
from mdcompose.core.exit_codes import EXIT_ATTENTION, EXIT_OK

Invoke = Callable[..., Invocation]

COMMIT_STYLE = "Prefer small commits.\n"
PYTHON_STYLE = "Use pathlib. Always specify encoding.\n"


@pytest.fixture
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A configured, populated library, isolated from the real machine."""
    config_directory = tmp_path / "config"
    config_directory.mkdir(parents=True)
    directory = config_directory / "snippets"
    directory.mkdir()
    (directory / "commit-style.md").write_text(
        "---\n"
        "title: Commit style\n"
        "description: How commits are written here\n"
        "tags: [git, conventions]\n"
        "category: conventions\n"
        "---\n\n" + COMMIT_STYLE,
        encoding="utf-8",
    )
    (directory / "python-style.md").write_text(
        "---\ntitle: Python style\ntags: [python]\ncategory: languages\n---\n\n" + PYTHON_STYLE,
        encoding="utf-8",
    )
    monkeypatch.setattr(platform_module, "config_dir", lambda: config_directory)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return directory


@pytest.fixture
def empty_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_directory = tmp_path / "config"
    monkeypatch.setattr(platform_module, "config_dir", lambda: config_directory)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return config_directory / "snippets"


def write_manifest(root: Path, entries: list[dict[str, object]]) -> Path:
    target = manifest_module.manifest_path(root)
    target.write_text(
        json.dumps(
            {
                "schema_version": manifest_module.SCHEMA_VERSION,
                "generated_by": "mdcompose 0.1.0",
                "generated_at": "2026-09-08T10:00:00Z",
                "detected_stack": [],
                "snippets": entries,
                "files": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def test_list_shows_every_snippet(invoke: Invoke, library: Path) -> None:
    result = invoke("snippet", "list")
    assert result.code == EXIT_OK
    assert "commit-style" in result.out
    assert "python-style" in result.out
    assert "How commits are written here" in result.out


def test_list_has_a_header_and_aligned_columns(invoke: Invoke, library: Path) -> None:
    lines = [ln for ln in invoke("snippet", "list").out.splitlines() if ln.strip()]
    assert lines[0].split() == ["id", "name", "description"]
    starts = {ln.index(ln.strip().split()[0]) for ln in lines}
    assert len(starts) == 1  # every row's first column starts at the same column


def test_list_on_an_empty_library_is_not_an_error(invoke: Invoke, empty_library: Path) -> None:
    result = invoke("snippet", "list")
    assert result.code == EXIT_OK
    assert "empty" in result.out


def test_list_on_an_empty_library_creates_nothing(invoke: Invoke, empty_library: Path) -> None:
    invoke("snippet", "list")
    assert not empty_library.exists()


def test_list_filters_by_tag(invoke: Invoke, library: Path) -> None:
    result = invoke("snippet", "list", "--tag", "python")
    assert "python-style" in result.out
    assert "commit-style" not in result.out


def test_list_filters_by_category(invoke: Invoke, library: Path) -> None:
    result = invoke("snippet", "list", "--category", "conventions")
    assert "commit-style" in result.out
    assert "python-style" not in result.out


def test_combined_filters_narrow(invoke: Invoke, library: Path) -> None:
    result = invoke("snippet", "list", "--tag", "python", "--category", "conventions")
    assert result.code == EXIT_OK
    assert "no snippet matches" in result.out


def test_a_filter_matching_nothing_is_not_an_error(invoke: Invoke, library: Path) -> None:
    result = invoke("snippet", "list", "--tag", "rust")
    assert result.code == EXIT_OK
    assert "no snippet matches" in result.out


def test_list_json_carries_the_metadata(invoke: Invoke, library: Path) -> None:
    payload = json.loads(invoke("snippet", "list", "--json").out)
    by_id = {entry["id"]: entry for entry in payload["snippets"]}
    assert by_id["commit-style"]["title"] == "Commit style"
    assert by_id["commit-style"]["tags"] == ["git", "conventions"]
    assert by_id["python-style"]["category"] == "languages"


def test_list_json_is_the_only_thing_on_stdout(invoke: Invoke, library: Path) -> None:
    assert json.loads(invoke("snippet", "list", "--json").out)["snippets"]


def test_list_json_on_an_empty_library(invoke: Invoke, empty_library: Path) -> None:
    payload = json.loads(invoke("snippet", "list", "--json").out)
    assert payload["snippets"] == []


def test_list_output_is_ascii(invoke: Invoke, library: Path) -> None:
    assert invoke("snippet", "list").out.isascii()


def test_edit_replaces_content_non_interactively(invoke: Invoke, library: Path) -> None:
    result = invoke(
        "snippet", "edit", "commit-style", "--content", "---\ntitle: New\n---\n\nNew body.\n"
    )
    assert result.code == EXIT_OK
    assert snippets_module.read(library / "commit-style.md").body == "New body.\n"


def test_edit_refuses_an_unknown_id_by_name(invoke: Invoke, library: Path) -> None:
    result = invoke("snippet", "edit", "absent", "--content", "x")
    assert result.code == EXIT_ATTENTION
    assert "absent" in result.err


def test_edit_rejects_content_that_would_not_parse(invoke: Invoke, library: Path) -> None:
    """A broken edit must leave the existing snippet exactly as it was."""
    before = (library / "commit-style.md").read_bytes()
    result = invoke(
        "snippet", "edit", "commit-style", "--content", "---\ntitle: [oops\n---\n\nB.\n"
    )
    assert result.code == EXIT_ATTENTION
    assert (library / "commit-style.md").read_bytes() == before


def test_edit_without_an_editor_configured_says_so(
    invoke: Invoke, library: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    result = invoke("snippet", "edit", "commit-style")
    assert result.code == EXIT_ATTENTION
    assert "no editor configured" in result.err


def _fake_editor(tmp_path: Path, script_body: str) -> str:
    """An EDITOR value: this interpreter running a script over the draft path."""
    script = tmp_path / "editor.py"
    script.write_text(textwrap.dedent(script_body), encoding="utf-8")
    return f'"{sys.executable}" "{script}"'


def test_edit_through_the_editor_writes_the_result(
    invoke: Invoke, library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "EDITOR",
        _fake_editor(
            tmp_path,
            """
            import pathlib, sys
            pathlib.Path(sys.argv[1]).write_text(
                "---\\ntitle: Edited\\n---\\n\\nEdited body.\\n", encoding="utf-8"
            )
            """,
        ),
    )
    result = invoke("snippet", "edit", "commit-style")
    assert result.code == EXIT_OK
    assert snippets_module.read(library / "commit-style.md").body == "Edited body.\n"


def test_edit_through_the_editor_with_no_change_is_reported(
    invoke: Invoke, library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EDITOR", _fake_editor(tmp_path, "pass\n"))
    result = invoke("snippet", "edit", "commit-style")
    assert result.code == EXIT_OK
    assert "unchanged" in result.out


def test_edit_reports_an_editor_that_exits_non_zero(
    invoke: Invoke, library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EDITOR", _fake_editor(tmp_path, "import sys; sys.exit(3)\n"))
    result = invoke("snippet", "edit", "commit-style")
    assert result.code == EXIT_ATTENTION
    assert "status 3" in result.err


def test_remove_deletes_the_snippet_when_confirmed(invoke: Invoke, library: Path) -> None:
    result = invoke("snippet", "remove", "commit-style", "--yes")
    assert result.code == EXIT_OK
    assert not (library / "commit-style.md").exists()
    assert (library / "python-style.md").exists()


def test_remove_refuses_an_unknown_id_by_name(invoke: Invoke, library: Path) -> None:
    result = invoke("snippet", "remove", "absent", "--yes")
    assert result.code == EXIT_ATTENTION
    assert "absent" in result.err


def test_remove_without_an_answer_refuses_rather_than_guessing(
    invoke: Invoke, library: Path
) -> None:
    """No terminal and no flag means the question cannot be answered safely."""
    result = invoke("snippet", "remove", "commit-style")
    assert result.code == EXIT_ATTENTION
    assert "--yes" in result.err
    assert (library / "commit-style.md").exists()


def test_remove_touches_no_project_file(invoke: Invoke, library: Path, tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "AGENTS.md").write_text("composed content\n", encoding="utf-8")
    before = (project / "AGENTS.md").read_bytes()
    invoke("snippet", "remove", "commit-style", "--yes")
    assert (project / "AGENTS.md").read_bytes() == before


def test_adopt_writes_embedded_snippets_into_an_empty_library(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [
            {"id": "from-project", "position": 0, "applies_to": "both", "content": "Theirs.\n"},
            {"id": "another", "position": 1, "applies_to": "agents", "content": "Also.\n"},
        ],
    )
    result = invoke("snippet", "adopt")
    assert result.code == EXIT_OK
    assert snippets_module.read(empty_library / "from-project.md").body == "Theirs.\n"
    assert snippets_module.read(empty_library / "another.md").applies_to == "agents"


def test_adopt_with_no_manifest_says_there_is_nothing_to_adopt(
    invoke: Invoke, empty_library: Path
) -> None:
    result = invoke("snippet", "adopt")
    assert result.code == EXIT_ATTENTION
    assert "nothing to adopt" in result.err


def test_adopt_reports_an_identical_snippet_as_already_present(
    invoke: Invoke, library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "commit-style", "position": 0, "applies_to": "both", "content": COMMIT_STYLE}],
    )
    before = (library / "commit-style.md").read_bytes()
    result = invoke("snippet", "adopt")
    assert result.code == EXIT_OK
    assert "already present" in result.out
    assert (library / "commit-style.md").read_bytes() == before


def test_identical_is_judged_under_normalization(
    invoke: Invoke, library: Path, tmp_path: Path
) -> None:
    """Otherwise every cross-platform checkout looks like a library of conflicts."""
    write_manifest(
        tmp_path / "project",
        [
            {
                "id": "commit-style",
                "position": 0,
                "applies_to": "both",
                "content": COMMIT_STYLE.replace("\n", "\r\n"),
            }
        ],
    )
    result = invoke("snippet", "adopt")
    assert "already present" in result.out


def test_adopt_keeps_the_local_copy_when_told_to(
    invoke: Invoke, library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "commit-style", "position": 0, "applies_to": "both", "content": "Different.\n"}],
    )
    before = (library / "commit-style.md").read_bytes()
    result = invoke("snippet", "adopt", "--on-collision", "keep")
    assert result.code == EXIT_OK
    assert (library / "commit-style.md").read_bytes() == before
    assert "kept" in result.out


def test_adopt_overwrites_when_told_to(invoke: Invoke, library: Path, tmp_path: Path) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "commit-style", "position": 0, "applies_to": "both", "content": "Different.\n"}],
    )
    result = invoke("snippet", "adopt", "--on-collision", "overwrite")
    assert result.code == EXIT_OK
    assert snippets_module.read(library / "commit-style.md").body == "Different.\n"


def test_a_collision_without_an_answer_refuses_rather_than_guessing(
    invoke: Invoke, library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "commit-style", "position": 0, "applies_to": "both", "content": "Different.\n"}],
    )
    before = (library / "commit-style.md").read_bytes()
    result = invoke("snippet", "adopt")
    assert result.code == EXIT_ATTENTION
    assert "--on-collision" in result.err
    assert (library / "commit-style.md").read_bytes() == before


def test_an_invalid_collision_answer_lists_the_options(
    invoke: Invoke, library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "commit-style", "position": 0, "applies_to": "both", "content": "Different.\n"}],
    )
    result = invoke("snippet", "adopt", "--on-collision", "sideways")
    assert result.code == EXIT_ATTENTION
    assert "overwrite" in result.err


def test_adopt_can_take_only_named_ids(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [
            {"id": "wanted", "position": 0, "applies_to": "both", "content": "Yes.\n"},
            {"id": "unwanted", "position": 1, "applies_to": "both", "content": "No.\n"},
        ],
    )
    result = invoke("snippet", "adopt", "wanted")
    assert result.code == EXIT_OK
    assert (empty_library / "wanted.md").exists()
    assert not (empty_library / "unwanted.md").exists()


def test_adopt_refuses_an_id_the_manifest_does_not_embed(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "present", "position": 0, "applies_to": "both", "content": "Yes.\n"}],
    )
    result = invoke("snippet", "adopt", "absent")
    assert result.code == EXIT_ATTENTION
    assert "absent" in result.err


def test_adopt_changes_no_project_file_or_manifest(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    (project / "AGENTS.md").write_text("composed\n", encoding="utf-8")
    manifest = write_manifest(
        project,
        [{"id": "one", "position": 0, "applies_to": "both", "content": "Body.\n"}],
    )
    before = {path.name: path.read_bytes() for path in project.iterdir()}
    invoke("snippet", "adopt")
    after = {path.name: path.read_bytes() for path in project.iterdir()}
    assert after == before
    assert manifest.read_bytes() == before[manifest.name]


def test_adopt_writes_only_snippet_files_into_the_library(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "one", "position": 0, "applies_to": "both", "content": "Body.\n"}],
    )
    invoke("snippet", "adopt")
    assert sorted(path.name for path in empty_library.iterdir()) == ["one.md"]


def test_an_adopted_snippet_is_immediately_listed(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "adopted", "position": 0, "applies_to": "both", "content": "Body.\n"}],
    )
    invoke("snippet", "adopt")
    assert "adopted" in invoke("snippet", "list").out


def test_adoption_is_never_automatic(invoke: Invoke, empty_library: Path, tmp_path: Path) -> None:
    """No other command may pull a stranger's snippets into a personal library."""
    write_manifest(
        tmp_path / "project",
        [{"id": "one", "position": 0, "applies_to": "both", "content": "Body.\n"}],
    )
    invoke("doctor")
    invoke("snippet", "list")
    assert not empty_library.exists() or list(empty_library.iterdir()) == []


def test_a_manifest_embedding_nothing_is_reported(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    write_manifest(tmp_path / "project", [])
    result = invoke("snippet", "adopt")
    assert result.code == EXIT_OK
    assert "embeds no snippets" in result.out


def test_the_library_ships_empty(invoke: Invoke, empty_library: Path) -> None:
    """mdcompose ships no snippets and offers no starter content."""
    result = invoke("snippet", "list")
    assert "empty" in result.out
    assert "example" not in result.out.lower()
    assert not empty_library.exists()


def test_snippet_help_is_ascii(invoke: Invoke) -> None:
    variants = (
        ("snippet", "--help"),
        ("snippet", "list", "--help"),
        ("snippet", "adopt", "--help"),
    )
    for args in variants:
        assert invoke(*args).out.isascii()


def test_every_snippet_command_offers_a_flag_for_its_prompt(invoke: Invoke) -> None:
    """The scriptability rule, checked at the surface."""
    assert "--yes" in invoke("snippet", "remove", "--help").out
    assert "--on-collision" in invoke("snippet", "adopt", "--help").out
    assert "--content" in invoke("snippet", "edit", "--help").out


def test_adopt_from_a_manifest_with_a_bom_and_crlf(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    manifest = write_manifest(
        project, [{"id": "one", "position": 0, "applies_to": "both", "content": "Body.\n"}]
    )
    manifest.write_bytes(
        (files.BOM + manifest.read_text(encoding="utf-8").replace("\n", "\r\n")).encode("utf-8")
    )
    result = invoke("snippet", "adopt")
    assert result.code == EXIT_OK
    assert (empty_library / "one.md").exists()
