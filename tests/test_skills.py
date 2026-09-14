"""The skill file format and the library write constraint."""

from __future__ import annotations

from pathlib import Path

import pytest

from mdcompose.core import files, skills
from mdcompose.core.exit_codes import AttentionError

FULL = """---
title: Code review
description: How we review code here
tags: [review, quality]
stack_signals: [pyproject.toml]
category: process
---

Review for correctness first, style second.
"""

BODY_ONLY = "Just a body, no frontmatter at all.\n"


def write_skill(library: Path, name: str, text: str) -> Path:
    library.mkdir(parents=True, exist_ok=True)
    target = library / f"{name}.md"
    target.write_text(text, encoding="utf-8")
    return target


def test_the_id_comes_from_the_filename(tmp_path: Path) -> None:
    path = write_skill(tmp_path, "code-review", FULL)
    assert skills.read(path).id == "code-review"


def test_there_is_no_id_field_to_drift(tmp_path: Path) -> None:
    path = write_skill(tmp_path, "code-review", FULL)
    renamed = path.with_name("reviewing.md")
    path.rename(renamed)
    assert skills.read(renamed).id == "reviewing"


def test_every_frontmatter_field_is_read(tmp_path: Path) -> None:
    skill = skills.read(write_skill(tmp_path, "code-review", FULL))
    assert skill.title == "Code review"
    assert skill.description == "How we review code here"
    assert skill.tags == ("review", "quality")
    assert skill.stack_signals == ("pyproject.toml",)
    assert skill.category == "process"


def test_the_body_excludes_the_frontmatter(tmp_path: Path) -> None:
    skill = skills.read(write_skill(tmp_path, "code-review", FULL))
    assert skill.body == "Review for correctness first, style second.\n"
    assert "title:" not in skill.body


def test_a_skill_with_no_frontmatter_is_valid(tmp_path: Path) -> None:
    skill = skills.read(write_skill(tmp_path, "bare", BODY_ONLY))
    assert skill.body == BODY_ONLY
    assert skill.display_name == "bare"


def test_an_empty_frontmatter_block_is_valid(tmp_path: Path) -> None:
    skill = skills.read(write_skill(tmp_path, "empty-meta", "---\n---\n\nBody.\n"))
    assert skill.body == "Body.\n"
    assert skill.title is None


@pytest.mark.parametrize(
    ("text", "field"),
    [
        ("---\ntags: review\n---\n\nB.\n", "tags"),
        ("---\nstack_signals: pyproject.toml\n---\n\nB.\n", "stack_signals"),
        ("---\ntitle: [a, b]\n---\n\nB.\n", "title"),
    ],
)
def test_a_wrong_typed_field_names_the_field(tmp_path: Path, text: str, field: str) -> None:
    path = write_skill(tmp_path, "broken", text)
    with pytest.raises(AttentionError) as raised:
        skills.read(path)
    assert field in str(raised.value)
    assert "broken" in str(raised.value)


def test_malformed_yaml_names_the_skill(tmp_path: Path) -> None:
    path = write_skill(tmp_path, "broken", "---\ntitle: [unclosed\n---\n\nB.\n")
    with pytest.raises(AttentionError) as raised:
        skills.read(path)
    assert "broken" in str(raised.value)


def test_an_unclosed_frontmatter_block_is_refused(tmp_path: Path) -> None:
    path = write_skill(tmp_path, "broken", "---\ntitle: X\n\nNo closing fence.\n")
    with pytest.raises(AttentionError) as raised:
        skills.read(path)
    assert "never closed" in str(raised.value)


def test_frontmatter_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    path = write_skill(tmp_path, "broken", "---\n- a list\n---\n\nB.\n")
    with pytest.raises(AttentionError) as raised:
        skills.read(path)
    assert "mapping" in str(raised.value)


def test_an_unrecognized_field_is_ignored(tmp_path: Path) -> None:
    text = "---\ntitle: X\nfuture_option: whatever\n---\n\nBody.\n"
    skill = skills.read(write_skill(tmp_path, "x", text))
    assert skill.title == "X"
    assert skill.body == "Body.\n"


def test_content_is_emitted_verbatim(tmp_path: Path) -> None:
    body = "Keep {{this}} and ${that} and {0} exactly as written.\n"
    skill = skills.read(write_skill(tmp_path, "literal", f"---\ntitle: L\n---\n\n{body}"))
    assert skill.body == body


def test_a_non_markdown_file_is_not_a_skill(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not a skill", encoding="utf-8")
    write_skill(tmp_path, "real", BODY_ONLY)
    assert [skill.id for skill in skills.load_library(tmp_path)] == ["real"]


def test_unrecognized_entries_are_skipped_without_complaint(tmp_path: Path) -> None:
    write_skill(tmp_path, "real", BODY_ONLY)
    (tmp_path / ".git").mkdir()
    (tmp_path / "subdir").mkdir()
    assert [skill.id for skill in skills.load_library(tmp_path)] == ["real"]


def test_reading_the_library_writes_nothing(tmp_path: Path) -> None:
    write_skill(tmp_path, "real", BODY_ONLY)
    before = sorted(path.name for path in tmp_path.iterdir())
    skills.load_library(tmp_path)
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_writing_a_skill_through_a_symlink_is_refused(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("not a skill\n", encoding="utf-8")
    try:
        (library / "planted.md").symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation not permitted here")

    skill = skills.parse(BODY_ONLY, "planted")
    with pytest.raises(AttentionError, match="symlink"):
        skills.write(library, skill)
    assert outside.read_text(encoding="utf-8") == "not a skill\n"


def test_an_absent_library_is_empty_not_an_error(tmp_path: Path) -> None:
    absent = tmp_path / "never-created"
    assert skills.load_library(absent) == ()
    assert not absent.exists()


def test_an_empty_library_is_empty_not_an_error(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    view = skills.view(tmp_path)
    assert view.is_empty
    assert view.skills == ()


def test_writing_a_skill_adds_only_that_file(tmp_path: Path) -> None:
    library = tmp_path / "library"
    skills.write(library, skills.Skill(id="one", body="Body.\n"))
    assert sorted(path.name for path in library.iterdir()) == ["one.md"]


def test_a_rendered_skill_round_trips(tmp_path: Path) -> None:
    original = skills.read(write_skill(tmp_path, "code-review", FULL))
    reparsed = skills.parse(skills.render(original), "code-review")
    assert reparsed.body == original.body
    assert reparsed.title == original.title
    assert reparsed.tags == original.tags


def test_a_minimal_skill_renders_without_a_frontmatter_block() -> None:
    rendered = skills.render(skills.Skill(id="bare", body="Body.\n"))
    assert rendered == "Body.\n"


@pytest.mark.parametrize("candidate", ["a/b", "..", "with space", "", ".hidden", "a\\b"])
def test_an_unusable_skill_name_is_refused(candidate: str) -> None:
    with pytest.raises(AttentionError):
        skills.validate_id(candidate)


@pytest.mark.parametrize("candidate", ["agents_md", "claude_md"])
def test_a_reserved_manifest_key_is_refused_as_a_skill_id(candidate: str) -> None:
    with pytest.raises(AttentionError, match="reserved"):
        skills.validate_id(candidate)


@pytest.mark.parametrize("candidate", ["code-review", "a", "a.b", "a_b", "A1"])
def test_a_usable_skill_name_is_accepted(candidate: str) -> None:
    assert skills.validate_id(candidate) == candidate


def test_filters_narrow_rather_than_widen(tmp_path: Path) -> None:
    write_skill(tmp_path, "one", "---\ntags: [review]\ncategory: process\n---\n\nB.\n")
    write_skill(tmp_path, "two", "---\ntags: [review]\ncategory: testing\n---\n\nB.\n")
    write_skill(tmp_path, "three", "---\ntags: [security]\ncategory: process\n---\n\nB.\n")
    library = skills.load_library(tmp_path)

    by_tag = skills.filter_skills(library, tag="review")
    by_category = skills.filter_skills(library, category="process")
    by_both = skills.filter_skills(library, tag="review", category="process")

    assert {s.id for s in by_tag} == {"one", "two"}
    assert {s.id for s in by_category} == {"one", "three"}
    assert {s.id for s in by_both} == {"one"}


def test_requiring_an_unknown_id_names_it(tmp_path: Path) -> None:
    view = skills.view(tmp_path)
    with pytest.raises(AttentionError) as raised:
        view.require("absent")
    assert "absent" in str(raised.value)


def test_a_skill_with_a_bom_reads_the_same(tmp_path: Path) -> None:
    path = tmp_path / "x.md"
    tmp_path.mkdir(exist_ok=True)
    path.write_bytes((files.BOM + FULL).encode("utf-8"))
    assert skills.read(path).title == "Code review"


def test_a_skill_with_crlf_reads_the_same(tmp_path: Path) -> None:
    path = tmp_path / "x.md"
    tmp_path.mkdir(exist_ok=True)
    path.write_bytes(FULL.replace("\n", "\r\n").encode("utf-8"))
    skill = skills.read(path)
    assert skill.title == "Code review"
    assert skill.body == "Review for correctness first, style second.\n"
