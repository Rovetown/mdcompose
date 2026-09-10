"""Section selection and target application for import, at the core level."""

from __future__ import annotations

from pathlib import Path

import pytest

from mdcompose.core import import_ops, library_ops, managed_block, sections, snippets
from mdcompose.core.exit_codes import AttentionError

SOURCE = """\
# One

first

# Two

second

## Two-a

nested

# Three

third
"""


def parsed() -> tuple[sections.Section, ...]:
    return sections.parse_sections(SOURCE, source_name="SOURCE.md")


# 4.1 the selection interface is a plain callable a stub can stand in for


def test_a_stub_selector_drives_the_selection() -> None:
    available = parsed()
    picked = [s for s in available if s.heading in {"Three", "One"}]
    result = import_ops.resolve_selection(
        available, requested_headings=None, selector=lambda _: picked
    )
    assert [s.heading for s in result] == ["One", "Three"]


def test_the_selector_result_is_returned_in_source_order() -> None:
    available = parsed()
    picked = list(reversed(available))
    result = import_ops.resolve_selection(
        available, requested_headings=None, selector=lambda _: picked
    )
    assert [s.heading for s in result] == [s.heading for s in available]


# 4.4 nothing selected


def test_selecting_nothing_returns_nothing() -> None:
    result = import_ops.resolve_selection(
        parsed(), requested_headings=None, selector=lambda _: []
    )
    assert result == ()


def test_no_selector_and_no_headings_is_refused() -> None:
    with pytest.raises(AttentionError, match="--section"):
        import_ops.resolve_selection(parsed(), requested_headings=None, selector=None)


# 4.3 named headings


def test_named_headings_resolve_in_source_order() -> None:
    result = import_ops.resolve_selection(
        parsed(), requested_headings=["Three", "One"], selector=None
    )
    assert [s.heading for s in result] == ["One", "Three"]


def test_an_unmatched_heading_is_named() -> None:
    with pytest.raises(AttentionError, match="Nope"):
        import_ops.match_headings(parsed(), ["One", "Nope"])


# 4.6 / 4.7 applying to a target


def test_apply_appends_outside_an_existing_managed_block(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    block_id = managed_block.AGENTS_COMPOSITION_BLOCK
    target.write_text(
        managed_block.upsert("# Mine\n\nkept\n", block_id, "composed\n", target),
        encoding="utf-8",
    )
    before = managed_block.read_blocks(target).find(block_id)

    import_ops.apply_to_target(target, "# Imported\n\nnew stuff\n")

    after = managed_block.read_blocks(target).find(block_id)
    assert after is not None and before is not None
    assert after.content == before.content
    text = target.read_text(encoding="utf-8")
    assert "# Imported" in text
    assert text.index("composed") < text.index("# Imported")


def test_apply_creates_a_missing_target_with_only_the_content(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    import_ops.apply_to_target(target, "# Imported\n\nnew stuff\n")
    assert target.read_text(encoding="utf-8") == "# Imported\n\nnew stuff\n"
    assert managed_block.read_blocks(target).blocks == ()


def test_apply_preserves_prior_content_verbatim(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("# Kept\n\nexactly this\n", encoding="utf-8")
    import_ops.apply_to_target(target, "added\n")
    assert target.read_text(encoding="utf-8") == "# Kept\n\nexactly this\n\nadded\n"


def test_apply_writes_nothing_for_empty_content(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    assert import_ops.apply_to_target(target, "\n\n") is False
    assert not target.exists()


# 5.2 / 5.2a build_snippet


def make_snippet(**overrides: object) -> snippets.Snippet:
    kwargs: dict[str, object] = {
        "name": "house-style",
        "body": "Body text.\n",
        "source_path": "/home/u/proj/CLAUDE.md",
        "source_heading": "House style",
        "category": "conventions",
        "tags": ("style", "python"),
        "today": "2026-09-09",
    }
    kwargs.update(overrides)
    return import_ops.build_snippet(**kwargs)  # type: ignore[arg-type]


def test_build_snippet_takes_its_title_from_the_source_heading() -> None:
    assert make_snippet().title == "House style"


def test_build_snippet_carries_category_and_tags() -> None:
    snippet = make_snippet()
    assert snippet.category == "conventions"
    assert snippet.tags == ("style", "python")


def test_build_snippet_records_all_three_provenance_fields() -> None:
    snippet = make_snippet()
    assert snippet.source_path == "/home/u/proj/CLAUDE.md"
    assert snippet.source_heading == "House style"
    assert snippet.imported_at == "2026-09-09"


def test_build_snippet_rejects_an_unusable_name() -> None:
    with pytest.raises(AttentionError):
        make_snippet(name="bad/name")


def test_provenance_is_optional_for_a_hand_written_snippet() -> None:
    minimal = snippets.Snippet(id="hand", body="just a body\n")
    rendered = snippets.render(minimal)
    assert "source_path" not in rendered
    reparsed = snippets.parse(rendered, "hand")
    assert reparsed.source_path is None and reparsed.imported_at is None


# 5.2b provenance never reaches composed output


def test_provenance_fields_are_not_in_the_rendered_body_section() -> None:
    snippet = make_snippet()
    rendered = snippets.render(snippet)
    _, body = rendered.split("---\n\n", 1)
    assert "source_path" not in body
    assert "imported_at" not in body


# 5.2c provenance survives an edit


def test_provenance_survives_a_body_edit(tmp_path: Path) -> None:
    library_dir = tmp_path / "snippets"
    snippet = make_snippet()
    snippets.write(library_dir, snippet)
    library = snippets.view(library_dir)

    edited = snippets.render(
        snippets.Snippet(
            id=snippet.id,
            body="a different body\n",
            title=snippet.title,
            category=snippet.category,
            tags=snippet.tags,
            source_path=snippet.source_path,
            source_heading=snippet.source_heading,
            imported_at=snippet.imported_at,
        )
    )
    library_ops.replace_body(library, snippet.id, edited)

    reread = snippets.read(library_dir / f"{snippet.id}.md")
    assert reread.body.strip() == "a different body"
    assert reread.source_path == "/home/u/proj/CLAUDE.md"
    assert reread.imported_at == "2026-09-09"


# 5.1 / 5.2d write_snippet


def test_write_snippet_writes_one_file_into_a_created_library(tmp_path: Path) -> None:
    library_dir = tmp_path / "does-not-exist-yet" / "snippets"
    library = snippets.view(library_dir)
    import_ops.write_snippet(library, make_snippet())
    assert [p.name for p in library_dir.iterdir()] == ["house-style.md"]


def test_write_snippet_refuses_an_existing_id_unless_overwriting(tmp_path: Path) -> None:
    library_dir = tmp_path / "snippets"
    snippets.write(library_dir, make_snippet())
    with pytest.raises(AttentionError, match="already exists"):
        import_ops.write_snippet(snippets.view(library_dir), make_snippet())
    import_ops.write_snippet(
        snippets.view(library_dir), make_snippet(body="new body\n"), overwrite=True
    )
    assert snippets.read(library_dir / "house-style.md").body.strip() == "new body"


# 6. collision status and rename


def test_snippet_status_is_new_for_an_absent_id(tmp_path: Path) -> None:
    library = snippets.view(tmp_path / "snippets")
    assert import_ops.snippet_status(library, make_snippet()) == import_ops.NEW


def test_snippet_status_is_identical_ignoring_line_endings(tmp_path: Path) -> None:
    library_dir = tmp_path / "snippets"
    snippets.write(library_dir, make_snippet(body="line one\nline two\n"))
    crlf = make_snippet(body="line one\r\nline two\r\n")
    assert import_ops.snippet_status(snippets.view(library_dir), crlf) == import_ops.IDENTICAL


def test_snippet_status_is_collision_for_a_different_body(tmp_path: Path) -> None:
    library_dir = tmp_path / "snippets"
    snippets.write(library_dir, make_snippet(body="original\n"))
    assert (
        import_ops.snippet_status(snippets.view(library_dir), make_snippet(body="changed\n"))
        == import_ops.COLLISION
    )


def test_rename_snippet_validates_the_new_id() -> None:
    renamed = import_ops.rename_snippet(make_snippet(), "house-style-2")
    assert renamed.id == "house-style-2"
    assert renamed.body == make_snippet().body
    with pytest.raises(AttentionError):
        import_ops.rename_snippet(make_snippet(), "bad/name")
