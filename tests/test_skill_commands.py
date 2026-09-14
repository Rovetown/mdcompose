"""The skill commands: list, edit, remove, adopt."""

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
from mdcompose.core import skills as skills_module
from mdcompose.core.exit_codes import EXIT_ATTENTION, EXIT_OK

Invoke = Callable[..., Invocation]

REVIEW_BODY = "Review for correctness first.\n"
RELEASE_BODY = "Tag, changelog, publish.\n"


@pytest.fixture
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A configured, populated skill library, isolated from the real machine."""
    config_directory = tmp_path / "config"
    config_directory.mkdir(parents=True)
    directory = config_directory / "skills"
    directory.mkdir()
    (directory / "code-review.md").write_text(
        "---\n"
        "title: Code review\n"
        "description: How we review code here\n"
        "tags: [review, quality]\n"
        "category: process\n"
        "---\n\n" + REVIEW_BODY,
        encoding="utf-8",
    )
    (directory / "release.md").write_text(
        "---\ntitle: Release\ntags: [release]\ncategory: process\n---\n\n" + RELEASE_BODY,
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
    return config_directory / "skills"


def write_manifest(root: Path, entries: list[dict[str, object]]) -> Path:
    target = manifest_module.manifest_path(root)
    target.write_text(
        json.dumps(
            {
                "schema_version": manifest_module.SCHEMA_VERSION,
                "generated_by": "mdcompose 0.2.0",
                "generated_at": "2026-09-14T10:00:00Z",
                "detected_stack": [],
                "snippets": [],
                "skills": entries,
                "files": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def test_list_shows_every_skill(invoke: Invoke, library: Path) -> None:
    result = invoke("skill", "list")
    assert result.code == EXIT_OK
    assert "code-review" in result.out
    assert "release" in result.out
    assert "How we review code here" in result.out


def test_list_has_a_header_and_aligned_columns(invoke: Invoke, library: Path) -> None:
    lines = [ln for ln in invoke("skill", "list").out.splitlines() if ln.strip()]
    assert lines[0].split() == ["id", "name", "description"]
    starts = {ln.index(ln.strip().split()[0]) for ln in lines}
    assert len(starts) == 1


def test_list_on_an_empty_library_is_not_an_error(invoke: Invoke, empty_library: Path) -> None:
    result = invoke("skill", "list")
    assert result.code == EXIT_OK
    assert "empty" in result.out


def test_list_on_an_empty_library_creates_nothing(invoke: Invoke, empty_library: Path) -> None:
    invoke("skill", "list")
    assert not empty_library.exists()


def test_list_filters_by_tag(invoke: Invoke, library: Path) -> None:
    result = invoke("skill", "list", "--tag", "review")
    assert "code-review" in result.out
    assert "release" not in result.out


def test_list_filters_by_category(invoke: Invoke, library: Path) -> None:
    result = invoke("skill", "list", "--category", "process")
    assert "code-review" in result.out
    assert "release" in result.out


def test_combined_filters_narrow(invoke: Invoke, library: Path) -> None:
    result = invoke("skill", "list", "--tag", "release", "--category", "process")
    assert result.code == EXIT_OK
    assert "release" in result.out
    assert "code-review" not in result.out


def test_a_filter_matching_nothing_is_not_an_error(invoke: Invoke, library: Path) -> None:
    result = invoke("skill", "list", "--tag", "rust")
    assert result.code == EXIT_OK
    assert "no skill matches" in result.out


def test_list_json_carries_the_metadata(invoke: Invoke, library: Path) -> None:
    payload = json.loads(invoke("skill", "list", "--json").out)
    by_id = {entry["id"]: entry for entry in payload["skills"]}
    assert by_id["code-review"]["title"] == "Code review"
    assert by_id["code-review"]["tags"] == ["review", "quality"]
    assert by_id["release"]["category"] == "process"


def test_list_json_is_the_only_thing_on_stdout(invoke: Invoke, library: Path) -> None:
    assert json.loads(invoke("skill", "list", "--json").out)["skills"]


def test_list_json_on_an_empty_library(invoke: Invoke, empty_library: Path) -> None:
    payload = json.loads(invoke("skill", "list", "--json").out)
    assert payload["skills"] == []


def test_list_output_is_ascii(invoke: Invoke, library: Path) -> None:
    assert invoke("skill", "list").out.isascii()


def test_edit_replaces_content_non_interactively(invoke: Invoke, library: Path) -> None:
    result = invoke(
        "skill", "edit", "code-review", "--content", "---\ntitle: New\n---\n\nNew body.\n"
    )
    assert result.code == EXIT_OK
    assert skills_module.read(library / "code-review.md").body == "New body.\n"


def test_edit_refuses_an_unknown_id_by_name(invoke: Invoke, library: Path) -> None:
    result = invoke("skill", "edit", "absent", "--content", "x")
    assert result.code == EXIT_ATTENTION
    assert "absent" in result.err


def test_edit_rejects_content_that_would_not_parse(invoke: Invoke, library: Path) -> None:
    before = (library / "code-review.md").read_bytes()
    result = invoke("skill", "edit", "code-review", "--content", "---\ntitle: [oops\n---\n\nB.\n")
    assert result.code == EXIT_ATTENTION
    assert (library / "code-review.md").read_bytes() == before


def test_edit_without_an_editor_configured_says_so(
    invoke: Invoke, library: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    result = invoke("skill", "edit", "code-review")
    assert result.code == EXIT_ATTENTION
    assert "no editor configured" in result.err


def _fake_editor(tmp_path: Path, script_body: str) -> str:
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
    result = invoke("skill", "edit", "code-review")
    assert result.code == EXIT_OK
    assert skills_module.read(library / "code-review.md").body == "Edited body.\n"


def test_edit_through_the_editor_with_no_change_is_reported(
    invoke: Invoke, library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EDITOR", _fake_editor(tmp_path, "pass\n"))
    result = invoke("skill", "edit", "code-review")
    assert result.code == EXIT_OK
    assert "unchanged" in result.out


def test_edit_reports_an_editor_that_exits_non_zero(
    invoke: Invoke, library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EDITOR", _fake_editor(tmp_path, "import sys; sys.exit(3)\n"))
    result = invoke("skill", "edit", "code-review")
    assert result.code == EXIT_ATTENTION
    assert "status 3" in result.err


def test_remove_deletes_the_skill_when_confirmed(invoke: Invoke, library: Path) -> None:
    result = invoke("skill", "remove", "code-review", "--yes")
    assert result.code == EXIT_OK
    assert not (library / "code-review.md").exists()
    assert (library / "release.md").exists()


def test_remove_refuses_an_unknown_id_by_name(invoke: Invoke, library: Path) -> None:
    result = invoke("skill", "remove", "absent", "--yes")
    assert result.code == EXIT_ATTENTION
    assert "absent" in result.err


def test_remove_without_an_answer_refuses_rather_than_guessing(
    invoke: Invoke, library: Path
) -> None:
    result = invoke("skill", "remove", "code-review")
    assert result.code == EXIT_ATTENTION
    assert "--yes" in result.err
    assert (library / "code-review.md").exists()


def test_remove_touches_no_project_file(invoke: Invoke, library: Path, tmp_path: Path) -> None:
    project = tmp_path / "project"
    skill_file = project / ".claude" / "skills" / "code-review" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("composed content\n", encoding="utf-8")
    before = skill_file.read_bytes()
    invoke("skill", "remove", "code-review", "--yes")
    assert skill_file.read_bytes() == before


def test_adopt_writes_embedded_skills_into_an_empty_library(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [
            {"id": "from-project", "position": 0, "content": "Theirs.\n"},
            {"id": "another", "position": 1, "content": "Also.\n"},
        ],
    )
    result = invoke("skill", "adopt")
    assert result.code == EXIT_OK
    assert skills_module.read(empty_library / "from-project.md").body == "Theirs.\n"
    assert skills_module.read(empty_library / "another.md").body == "Also.\n"


def test_adopt_with_no_manifest_says_there_is_nothing_to_adopt(
    invoke: Invoke, empty_library: Path
) -> None:
    result = invoke("skill", "adopt")
    assert result.code == EXIT_ATTENTION
    assert "nothing to adopt" in result.err


def test_adopt_reports_an_identical_skill_as_already_present(
    invoke: Invoke, library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "code-review", "position": 0, "content": REVIEW_BODY}],
    )
    before = (library / "code-review.md").read_bytes()
    result = invoke("skill", "adopt")
    assert result.code == EXIT_OK
    assert "already present" in result.out
    assert (library / "code-review.md").read_bytes() == before


def test_identical_is_judged_under_normalization(
    invoke: Invoke, library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "code-review", "position": 0, "content": REVIEW_BODY.replace("\n", "\r\n")}],
    )
    result = invoke("skill", "adopt")
    assert "already present" in result.out


def test_adopt_keeps_the_local_copy_when_told_to(
    invoke: Invoke, library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "code-review", "position": 0, "content": "Different.\n"}],
    )
    before = (library / "code-review.md").read_bytes()
    result = invoke("skill", "adopt", "--on-collision", "keep")
    assert result.code == EXIT_OK
    assert (library / "code-review.md").read_bytes() == before
    assert "kept" in result.out


def test_adopt_overwrites_when_told_to(invoke: Invoke, library: Path, tmp_path: Path) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "code-review", "position": 0, "content": "Different.\n"}],
    )
    result = invoke("skill", "adopt", "--on-collision", "overwrite")
    assert result.code == EXIT_OK
    assert skills_module.read(library / "code-review.md").body == "Different.\n"


def test_a_collision_without_an_answer_refuses_rather_than_guessing(
    invoke: Invoke, library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "code-review", "position": 0, "content": "Different.\n"}],
    )
    before = (library / "code-review.md").read_bytes()
    result = invoke("skill", "adopt")
    assert result.code == EXIT_ATTENTION
    assert "--on-collision" in result.err
    assert (library / "code-review.md").read_bytes() == before


def test_an_invalid_collision_answer_lists_the_options(
    invoke: Invoke, library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "code-review", "position": 0, "content": "Different.\n"}],
    )
    result = invoke("skill", "adopt", "--on-collision", "sideways")
    assert result.code == EXIT_ATTENTION
    assert "overwrite" in result.err


def test_adopt_can_take_only_named_ids(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [
            {"id": "wanted", "position": 0, "content": "Yes.\n"},
            {"id": "unwanted", "position": 1, "content": "No.\n"},
        ],
    )
    result = invoke("skill", "adopt", "wanted")
    assert result.code == EXIT_OK
    assert (empty_library / "wanted.md").exists()
    assert not (empty_library / "unwanted.md").exists()


def test_adopt_refuses_an_id_the_manifest_does_not_embed(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "present", "position": 0, "content": "Yes.\n"}],
    )
    result = invoke("skill", "adopt", "absent")
    assert result.code == EXIT_ATTENTION
    assert "absent" in result.err


def test_adopt_changes_no_project_file_or_manifest(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    (project / "AGENTS.md").write_text("composed\n", encoding="utf-8")
    manifest = write_manifest(
        project,
        [{"id": "one", "position": 0, "content": "Body.\n"}],
    )
    before = {path.name: path.read_bytes() for path in project.iterdir()}
    invoke("skill", "adopt")
    after = {path.name: path.read_bytes() for path in project.iterdir()}
    assert after == before
    assert manifest.read_bytes() == before[manifest.name]


def test_adopt_writes_only_skill_files_into_the_library(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "one", "position": 0, "content": "Body.\n"}],
    )
    invoke("skill", "adopt")
    assert sorted(path.name for path in empty_library.iterdir()) == ["one.md"]


def test_an_adopted_skill_is_immediately_listed(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "adopted", "position": 0, "content": "Body.\n"}],
    )
    invoke("skill", "adopt")
    assert "adopted" in invoke("skill", "list").out


def test_adoption_is_never_automatic(invoke: Invoke, empty_library: Path, tmp_path: Path) -> None:
    write_manifest(
        tmp_path / "project",
        [{"id": "one", "position": 0, "content": "Body.\n"}],
    )
    invoke("doctor")
    invoke("skill", "list")
    assert not empty_library.exists() or list(empty_library.iterdir()) == []


def test_a_manifest_embedding_no_skills_is_reported(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    write_manifest(tmp_path / "project", [])
    result = invoke("skill", "adopt")
    assert result.code == EXIT_OK
    assert "embeds no skills" in result.out


def test_the_library_ships_empty(invoke: Invoke, empty_library: Path) -> None:
    result = invoke("skill", "list")
    assert "empty" in result.out
    assert "example" not in result.out.lower()
    assert not empty_library.exists()


def test_skill_help_is_ascii(invoke: Invoke) -> None:
    variants = (
        ("skill", "--help"),
        ("skill", "list", "--help"),
        ("skill", "adopt", "--help"),
    )
    for args in variants:
        assert invoke(*args).out.isascii()


def test_every_skill_command_offers_a_flag_for_its_prompt(invoke: Invoke) -> None:
    assert "--yes" in invoke("skill", "remove", "--help").out
    assert "--on-collision" in invoke("skill", "adopt", "--help").out
    assert "--content" in invoke("skill", "edit", "--help").out


def test_adopt_from_a_manifest_with_a_bom_and_crlf(
    invoke: Invoke, empty_library: Path, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    manifest = write_manifest(project, [{"id": "one", "position": 0, "content": "Body.\n"}])
    manifest.write_bytes(
        (files.BOM + manifest.read_text(encoding="utf-8").replace("\n", "\r\n")).encode("utf-8")
    )
    result = invoke("skill", "adopt")
    assert result.code == EXIT_OK
    assert (empty_library / "one.md").exists()


def test_top_level_help_lists_skill_group(invoke: Invoke) -> None:
    assert "skill" in invoke("--help").out
