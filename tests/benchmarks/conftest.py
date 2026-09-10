"""Builders for the benchmark inputs.

Kept apart from the main test conftest so the normal suite never imports the
benchmark plugins. Everything here produces a large but valid input for one
core operation; nothing here asserts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mdcompose.core import files, managed_block

AGENTS_BLOCK = managed_block.AGENTS_COMPOSITION_BLOCK
CLAUDE_BLOCK = managed_block.CLAUDE_MANAGED_BLOCK


def _markdown_of_size(target_bytes: int) -> str:
    """A markdown document of roughly ``target_bytes``, many headings deep."""
    parts: list[str] = ["Intro prose before the first heading.\n\n"]
    section = 0
    while sum(len(part) for part in parts) < target_bytes:
        section += 1
        level = "#" * (2 + section % 3)
        parts.append(f"{level} Section {section}\n\n")
        parts.append(
            f"Body line for section {section}. " * 6 + "\n\n"
            f"- point one for {section}\n- point two for {section}\n\n"
        )
    return "".join(parts)


@pytest.fixture(scope="session")
def large_markdown() -> str:
    """About 200 KB of headed markdown, for the section parser."""
    return _markdown_of_size(200_000)


@pytest.fixture(scope="session")
def large_claude_md() -> str:
    """A CLAUDE.md whose managed block holds about 200 KB of content."""
    body = _markdown_of_size(200_000)
    return managed_block.upsert(
        "Hand-written notes above the block.\n\n", CLAUDE_BLOCK, body, Path("CLAUDE.md")
    )


@pytest.fixture
def library_dir(tmp_path: Path) -> Path:
    """A snippet library directory holding 300 small valid snippets."""
    directory = tmp_path / "library"
    directory.mkdir()
    for index in range(300):
        (directory / f"snippet-{index:03d}.md").write_text(
            "---\n"
            f"title: Snippet {index}\n"
            "applies_to: both\n"
            f"tags: [tag{index % 10}, common]\n"
            "---\n\n"
            f"Guidance number {index}. " * 8 + "\n",
            encoding="utf-8",
        )
    return directory


@pytest.fixture
def drifted_project(tmp_path: Path, large_claude_md: str) -> Path:
    """A project whose AGENTS.md and CLAUDE.md carry large managed blocks."""
    root = tmp_path / "project"
    root.mkdir()
    composed = _markdown_of_size(200_000)
    agents = managed_block.upsert(
        "User prose.\n\n", AGENTS_BLOCK, composed, root / "AGENTS.md"
    )
    (root / "AGENTS.md").write_text(agents, encoding="utf-8")
    (root / "CLAUDE.md").write_text(large_claude_md, encoding="utf-8")

    agents_hash = files.hash_content(composed)
    claude_hash = files.hash_content(
        managed_block.read_blocks(root / "CLAUDE.md").find(CLAUDE_BLOCK).content
    )
    (root / "mdcompose.lock").write_text(
        "{\n"
        f'  "schema_version": 1,\n'
        f'  "generated_by": "mdcompose 0.1.0",\n'
        f'  "generated_at": "2026-09-08T10:00:00Z",\n'
        f'  "detected_stack": [],\n'
        f'  "snippets": [],\n'
        f'  "files": {{\n'
        f'    "agents_md": {{"path": "AGENTS.md", "mode": "copy", '
        f'"managed_block_hash": "{agents_hash}"}},\n'
        f'    "claude_md": {{"path": "CLAUDE.md", "mode": "copy", '
        f'"managed_block_hash": "{claude_hash}"}}\n'
        f"  }}\n"
        "}\n",
        encoding="utf-8",
    )
    return root
