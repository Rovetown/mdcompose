"""Writing one selected skill into its own `.claude/skills/<id>/SKILL.md`.

Mirrors ``composition.py``'s role for AGENTS.md/CLAUDE.md, but a skill is
never blended with another skill's body the way several snippets share one
block: each selected skill becomes its own complete file.

That difference is also why a skill file needs its own write path rather than
``composition.apply_to_file`` unchanged. Claude Code requires a SKILL.md's
`name`/`description` frontmatter to be the file's first bytes, so it cannot
live inside the managed block the way AGENTS.md's composed content does; it
sits before the block instead. But ``apply_to_file``'s whole reason to exist
is preserving everything outside the block untouched, which is exactly wrong
for frontmatter that must track the library on every run. So writing a skill
file additionally regenerates the region before the block on every write,
while everything from the block onward (the block itself, and anything a
user appended after it) keeps the ordinary preserve-and-hash treatment.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from mdcompose.core import files, managed_block
from mdcompose.core.skills import Skill

SKILL_FILENAME = "SKILL.md"
SKILLS_DIR_NAME = "skills"
CLAUDE_DIR_NAME = ".claude"


def skill_path(root: Path, skill_id: str) -> Path:
    """Where a composed skill's file lives inside a target directory."""
    return root / CLAUDE_DIR_NAME / SKILLS_DIR_NAME / skill_id / SKILL_FILENAME


def render_frontmatter(skill: Skill) -> str:
    """The `name`/`description` frontmatter mdcompose generates for a SKILL.md.

    Regenerated from the library on every write, unlike a managed block's
    content, which changes only when the selection or the library entry does.
    """
    metadata: dict[str, object] = {"name": skill.id}
    if skill.description is not None:
        metadata["description"] = skill.description
    block = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return f"---\n{block}---"


def apply_to_file(path: Path, block_id: str, content: str, frontmatter: str) -> bool:
    """Write one skill file: generated frontmatter, then the managed block.

    Returns whether anything changed, so a repeat run with the same selection
    and the same library entry is a no-op rather than a rewrite. Unlike
    ``composition.apply_to_file``, the region before the managed block is not
    preserved: it is mdcompose's own frontmatter, replaced every run.
    """
    existing = files.read_text(path) if files.path_exists(path) and path.is_file() else ""
    updated_block = managed_block.upsert(existing, block_id, content, path)
    updated = _with_frontmatter(updated_block, block_id, frontmatter, path)
    if existing and files.content_equal(existing, updated):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    files.write_text(path, updated, line_ending=files.line_ending_for(path))
    return True


def _with_frontmatter(text: str, block_id: str, frontmatter: str, source: Path) -> str:
    """Replace everything before the block's start marker with ``frontmatter``.

    Everything from the start marker onward, including the block and any
    content a user appended after it, is left exactly as ``upsert`` produced
    it.
    """
    blocks = managed_block.parse(text, source)
    block = next(item for item in blocks if item.block_id == block_id)
    lines = files.normalize(text).split("\n")
    from_marker = lines[block.start_line - 1 :]
    frontmatter_lines = frontmatter.rstrip("\n").split("\n")
    return "\n".join([*frontmatter_lines, "", *from_marker])
