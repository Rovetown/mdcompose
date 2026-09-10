"""The managed block: marker recognition, boundaries, malformed cases, hashing."""

from __future__ import annotations

from pathlib import Path

import pytest

from mdcompose.core import files, managed_block
from mdcompose.core.exit_codes import AttentionError

BLOCK = "agents-composition"
START = managed_block.start_marker(BLOCK)
END = managed_block.end_marker(BLOCK)

WELL_FORMED = f"""# Project notes

Some prose the user wrote.

{START}
Composed line one.
Composed line two.
{END}

More prose the user wrote.
"""


def test_marker_strings_are_exactly_this() -> None:
    """The marker format is a compatibility surface. This test locks it.

    Changing either string orphans every block already written into a user's
    files, and mdcompose would silently treat a managed region as user text.
    """
    assert START == "<!-- mdcompose:agents-composition:start -->"
    assert END == "<!-- mdcompose:agents-composition:end -->"


def test_markers_are_html_comments_so_they_render_as_nothing() -> None:
    for marker in (START, END):
        assert marker.startswith("<!--")
        assert marker.endswith("-->")


def test_a_well_formed_block_is_recognized() -> None:
    result = managed_block.scan(WELL_FORMED)
    assert result.is_well_formed
    block = result.find(BLOCK)
    assert block is not None
    assert block.block_id == BLOCK


def test_content_is_the_lines_strictly_between_the_markers() -> None:
    block = managed_block.scan(WELL_FORMED).find(BLOCK)
    assert block is not None
    assert block.content == "Composed line one.\nComposed line two.\n"
    assert "mdcompose:" not in block.content


def test_marker_lines_are_reported_for_error_messages() -> None:
    block = managed_block.scan(WELL_FORMED).find(BLOCK)
    assert block is not None
    assert block.start_line == 5
    assert block.end_line == 8


def test_an_empty_block_is_valid() -> None:
    result = managed_block.scan(f"{START}\n{END}\n")
    block = result.find(BLOCK)
    assert result.is_well_formed
    assert block is not None
    assert block.content == ""


def test_a_block_at_the_very_start_and_end_of_a_file_is_recognized() -> None:
    block = managed_block.scan(f"{START}\nonly line\n{END}").find(BLOCK)
    assert block is not None
    assert block.content == "only line\n"


def test_an_indented_marker_is_still_a_marker() -> None:
    result = managed_block.scan(f"    {START}\n  content\n\t{END}\n")
    assert result.is_well_formed
    assert result.find(BLOCK) is not None


@pytest.mark.parametrize(
    "line",
    [
        f"text before {START}",
        f"{START} text after",
        f"> {START}",
        f"- {START}",
    ],
)
def test_a_marker_sharing_its_line_is_not_a_marker(line: str) -> None:
    result = managed_block.scan(f"{line}\ncontent\n{END}\n")
    assert result.find(BLOCK) is None


def test_a_marker_inside_a_code_fence_is_documentation_not_a_marker() -> None:
    """Otherwise anyone documenting the format breaks their own file."""
    text = f"""# How mdcompose marks its region

```markdown
{START}
composed content goes here
{END}
```

Nothing above is a real marker.
"""
    result = managed_block.scan(text)
    assert result.is_well_formed
    assert result.blocks == ()


def test_a_real_block_survives_a_fenced_example_in_the_same_file() -> None:
    text = f"""# Notes

```
{START}
{END}
```

{START}
the real content
{END}
"""
    result = managed_block.scan(text)
    assert result.is_well_formed
    block = result.find(BLOCK)
    assert block is not None
    assert block.content == "the real content\n"


def test_a_fence_closes_and_scanning_resumes() -> None:
    text = f"""```
not a marker here
```

{START}
real
{END}
"""
    assert managed_block.scan(text).find(BLOCK) is not None


def test_a_fence_is_not_closed_by_a_different_character() -> None:
    text = f"""```
~~~
{START}
{END}
"""
    result = managed_block.scan(text)
    assert result.is_well_formed
    assert result.blocks == ()


def test_tilde_fences_work_too() -> None:
    text = f"""~~~
{START}
~~~

{START}
real
{END}
"""
    block = managed_block.scan(text).find(BLOCK)
    assert block is not None
    assert block.content == "real\n"


def test_two_distinct_blocks_in_one_file_are_both_recognized() -> None:
    other_start = managed_block.start_marker("claude-managed")
    other_end = managed_block.end_marker("claude-managed")
    text = f"{START}\nfirst\n{END}\n\nprose\n\n{other_start}\nsecond\n{other_end}\n"
    result = managed_block.scan(text)
    assert result.is_well_formed
    assert len(result.blocks) == 2
    assert result.find("claude-managed") is not None


def test_a_start_with_no_end_is_malformed() -> None:
    result = managed_block.scan(f"# Title\n\n{START}\ncontent\n")
    assert result.problem is not None
    assert result.problem.kind == "unmatched-start"
    assert BLOCK in result.problem.message
    assert "3" in result.problem.message


def test_an_end_before_its_start_is_malformed() -> None:
    result = managed_block.scan(f"{END}\ncontent\n{START}\n")
    assert result.problem is not None
    assert result.problem.kind == "unmatched-end"
    assert BLOCK in result.problem.message


def test_two_complete_blocks_with_one_id_are_malformed() -> None:
    """Both start lines are named, so the user can see which two collide."""
    doubled = WELL_FORMED + WELL_FORMED
    start_lines = [
        number for number, line in enumerate(doubled.splitlines(), start=1) if line == START
    ]
    result = managed_block.scan(doubled)
    assert result.problem is not None
    assert result.problem.kind == "duplicate-id"
    for number in start_lines:
        assert str(number) in result.problem.message


def test_a_repeated_start_before_any_end_is_malformed() -> None:
    result = managed_block.scan(f"{START}\n{START}\n{END}\n")
    assert result.problem is not None
    assert result.problem.kind == "duplicate-id"


def test_nested_blocks_are_malformed_and_name_both_ids() -> None:
    inner_start = managed_block.start_marker("claude-managed")
    inner_end = managed_block.end_marker("claude-managed")
    result = managed_block.scan(f"{START}\n{inner_start}\nx\n{inner_end}\n{END}\n")
    assert result.problem is not None
    assert result.problem.kind == "nested"
    assert BLOCK in result.problem.message
    assert "claude-managed" in result.problem.message


def test_scan_never_raises_on_malformed_input() -> None:
    """A reporting command must be able to list a bad file beside good ones."""
    for text in (f"{START}\n", f"{END}\n", f"{START}\n{START}\n{END}\n"):
        assert managed_block.scan(text).problem is not None


def test_parse_raises_and_names_the_file(tmp_path: Path) -> None:
    """A write path must refuse a file whose boundaries cannot be determined."""
    source = tmp_path / "AGENTS.md"
    with pytest.raises(AttentionError) as raised:
        managed_block.parse(f"{START}\ncontent\n", source)
    message = str(raised.value)
    assert "AGENTS.md" in message
    assert BLOCK in message


def test_parse_returns_blocks_when_well_formed(tmp_path: Path) -> None:
    blocks = managed_block.parse(WELL_FORMED, tmp_path / "AGENTS.md")
    assert len(blocks) == 1


def test_reading_a_file_scans_it(tmp_path: Path) -> None:
    source = tmp_path / "AGENTS.md"
    source.write_text(WELL_FORMED, encoding="utf-8")
    assert managed_block.read_blocks(source).find(BLOCK) is not None


def test_reading_never_modifies_the_file(tmp_path: Path) -> None:
    source = tmp_path / "AGENTS.md"
    source.write_bytes(WELL_FORMED.encode("utf-8"))
    before = source.read_bytes()
    managed_block.read_blocks(source)
    assert source.read_bytes() == before


def test_a_file_with_no_block_is_not_an_error(tmp_path: Path) -> None:
    source = tmp_path / "AGENTS.md"
    source.write_text("# Just prose\n\nNothing managed here.\n", encoding="utf-8")
    result = managed_block.read_blocks(source)
    assert result.is_well_formed
    assert result.blocks == ()


def block_hash(text: str) -> str:
    block = managed_block.scan(text).find(BLOCK)
    assert block is not None
    return block.content_hash


def test_hash_ignores_everything_outside_the_block() -> None:
    changed = WELL_FORMED.replace("Some prose the user wrote.", "Completely different prose.")
    assert block_hash(changed) == block_hash(WELL_FORMED)


def test_hash_changes_when_the_content_changes() -> None:
    changed = WELL_FORMED.replace("Composed line one.", "Composed line ONE.")
    assert block_hash(changed) != block_hash(WELL_FORMED)


def test_hash_ignores_line_endings() -> None:
    assert block_hash(WELL_FORMED.replace("\n", "\r\n")) == block_hash(WELL_FORMED)


def test_hash_ignores_a_byte_order_mark() -> None:
    assert block_hash(files.BOM + WELL_FORMED) == block_hash(WELL_FORMED)


def test_hash_ignores_marker_indentation_and_surrounding_blank_lines() -> None:
    reindented = WELL_FORMED.replace(START, f"   {START}").replace(END, f"  {END}")
    spaced = reindented.replace(f"   {START}", f"\n   {START}")
    assert block_hash(spaced) == block_hash(WELL_FORMED)


def test_hash_is_comparable_across_platforms() -> None:
    """Two machines composing the same content must agree, or a committed
    manifest would report drift on a file nobody touched."""
    windows_checkout = files.BOM + WELL_FORMED.replace("\n", "\r\n")
    linux_checkout = WELL_FORMED
    assert block_hash(windows_checkout) == block_hash(linux_checkout)
