"""Writing a skill's frontmatter and managed block into its own SKILL.md."""

from __future__ import annotations

from pathlib import Path

from mdcompose.core import managed_block, skill_composition
from mdcompose.core.skills import Skill

BLOCK = managed_block.SKILL_MANAGED_BLOCK


def test_frontmatter_carries_name_and_description() -> None:
    frontmatter = skill_composition.render_frontmatter(
        Skill(id="code-review", body="Body.\n", description="How we review code")
    )
    assert frontmatter.startswith("---\n")
    assert "name: code-review" in frontmatter
    assert "description: How we review code" in frontmatter


def test_frontmatter_omits_description_when_absent() -> None:
    frontmatter = skill_composition.render_frontmatter(Skill(id="bare", body="Body.\n"))
    assert "name: bare" in frontmatter
    assert "description" not in frontmatter


def test_a_new_skill_file_is_written_with_frontmatter_then_block(tmp_path: Path) -> None:
    target = tmp_path / "SKILL.md"
    frontmatter = skill_composition.render_frontmatter(Skill(id="x", body="B\n"))
    changed = skill_composition.apply_to_file(target, BLOCK, "Body content.\n", frontmatter)
    assert changed is True
    text = target.read_text(encoding="utf-8")
    assert text.startswith("---\nname: x\n---\n\n")
    assert managed_block.start_marker(BLOCK) in text
    assert "Body content.\n" in text


def test_a_repeat_write_with_no_change_is_a_no_op(tmp_path: Path) -> None:
    target = tmp_path / "SKILL.md"
    frontmatter = skill_composition.render_frontmatter(Skill(id="x", body="B\n"))
    skill_composition.apply_to_file(target, BLOCK, "Body.\n", frontmatter)
    changed = skill_composition.apply_to_file(target, BLOCK, "Body.\n", frontmatter)
    assert changed is False


def test_frontmatter_is_regenerated_even_when_the_block_is_unchanged(tmp_path: Path) -> None:
    """A description-only change must still rewrite the file."""
    target = tmp_path / "SKILL.md"
    skill_composition.apply_to_file(
        target, BLOCK, "Body.\n", skill_composition.render_frontmatter(Skill(id="x", body="B\n"))
    )
    updated_frontmatter = skill_composition.render_frontmatter(
        Skill(id="x", body="B\n", description="Now with a description")
    )
    changed = skill_composition.apply_to_file(target, BLOCK, "Body.\n", updated_frontmatter)
    assert changed is True
    text = target.read_text(encoding="utf-8")
    assert "description: Now with a description" in text
    assert "Body.\n" in text


def test_content_after_the_block_survives_a_frontmatter_regeneration(tmp_path: Path) -> None:
    target = tmp_path / "SKILL.md"
    skill_composition.apply_to_file(
        target, BLOCK, "Body.\n", skill_composition.render_frontmatter(Skill(id="x", body="B\n"))
    )
    with_trailer = target.read_text(encoding="utf-8") + "\nMy own notes after the block.\n"
    target.write_text(with_trailer, encoding="utf-8")

    changed = skill_composition.apply_to_file(
        target,
        BLOCK,
        "Body.\n",
        skill_composition.render_frontmatter(Skill(id="x", body="B\n", description="d")),
    )
    assert changed is True
    text = target.read_text(encoding="utf-8")
    assert "My own notes after the block." in text
    assert "description: d" in text


def test_skill_path_lives_under_dot_claude_skills(tmp_path: Path) -> None:
    path = skill_composition.skill_path(tmp_path, "code-review")
    assert path == tmp_path / ".claude" / "skills" / "code-review" / "SKILL.md"
