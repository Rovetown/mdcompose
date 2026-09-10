"""The snippet file format, the library write constraint, and ordering."""

from __future__ import annotations

from pathlib import Path

import pytest

from mdcompose.core import files, snippets
from mdcompose.core.exit_codes import AttentionError

FULL = """---
title: Python style
description: How we write Python here
tags: [python, style]
applies_to: both
stack_signals: [pyproject.toml]
category: conventions
order: 10
---

Use pathlib. Always specify encoding.
"""

BODY_ONLY = "Just a body, no frontmatter at all.\n"


def write_snippet(library: Path, name: str, text: str) -> Path:
    library.mkdir(parents=True, exist_ok=True)
    target = library / f"{name}.md"
    target.write_text(text, encoding="utf-8")
    return target


def test_the_id_comes_from_the_filename(tmp_path: Path) -> None:
    path = write_snippet(tmp_path, "python-style", FULL)
    assert snippets.read(path).id == "python-style"


def test_there_is_no_id_field_to_drift(tmp_path: Path) -> None:
    """Two sources of identity would disagree the first time a file is renamed."""
    path = write_snippet(tmp_path, "python-style", FULL)
    renamed = path.with_name("house-style.md")
    path.rename(renamed)
    assert snippets.read(renamed).id == "house-style"


def test_every_frontmatter_field_is_read(tmp_path: Path) -> None:
    snippet = snippets.read(write_snippet(tmp_path, "python-style", FULL))
    assert snippet.title == "Python style"
    assert snippet.description == "How we write Python here"
    assert snippet.tags == ("python", "style")
    assert snippet.applies_to == "both"
    assert snippet.stack_signals == ("pyproject.toml",)
    assert snippet.category == "conventions"
    assert snippet.order == 10


def test_the_body_excludes_the_frontmatter(tmp_path: Path) -> None:
    snippet = snippets.read(write_snippet(tmp_path, "python-style", FULL))
    assert snippet.body == "Use pathlib. Always specify encoding.\n"
    assert "title:" not in snippet.body


def test_a_snippet_with_no_frontmatter_is_valid(tmp_path: Path) -> None:
    """The barrier to writing a snippet should be no higher than writing markdown."""
    snippet = snippets.read(write_snippet(tmp_path, "bare", BODY_ONLY))
    assert snippet.body == BODY_ONLY
    assert snippet.applies_to == snippets.DEFAULT_APPLIES_TO
    assert snippet.display_name == "bare"


def test_an_empty_frontmatter_block_is_valid(tmp_path: Path) -> None:
    snippet = snippets.read(write_snippet(tmp_path, "empty-meta", "---\n---\n\nBody.\n"))
    assert snippet.body == "Body.\n"
    assert snippet.title is None


def test_applies_to_defaults_to_both(tmp_path: Path) -> None:
    snippet = snippets.read(write_snippet(tmp_path, "x", "---\ntitle: X\n---\n\nBody.\n"))
    assert snippet.applies_to == "both"
    assert snippet.applies_to_agents()
    assert snippet.applies_to_claude()


@pytest.mark.parametrize(
    ("value", "agents", "claude"),
    [("agents", True, False), ("claude", False, True), ("both", True, True)],
)
def test_applies_to_controls_eligibility(
    tmp_path: Path, value: str, agents: bool, claude: bool
) -> None:
    text = f"---\napplies_to: {value}\n---\n\nBody.\n"
    snippet = snippets.read(write_snippet(tmp_path, "x", text))
    assert snippet.applies_to_agents() is agents
    assert snippet.applies_to_claude() is claude


def test_an_invalid_applies_to_names_the_snippet_and_the_value(tmp_path: Path) -> None:
    path = write_snippet(tmp_path, "sideways", "---\napplies_to: sideways\n---\n\nBody.\n")
    with pytest.raises(AttentionError) as raised:
        snippets.read(path)
    message = str(raised.value)
    assert "sideways" in message
    assert "agents" in message


@pytest.mark.parametrize(
    ("text", "field"),
    [
        ("---\ntags: python\n---\n\nB.\n", "tags"),
        ("---\nstack_signals: pyproject.toml\n---\n\nB.\n", "stack_signals"),
        ("---\ntitle: [a, b]\n---\n\nB.\n", "title"),
        ("---\norder: first\n---\n\nB.\n", "order"),
        ("---\norder: true\n---\n\nB.\n", "order"),
    ],
)
def test_a_wrong_typed_field_names_the_field(tmp_path: Path, text: str, field: str) -> None:
    path = write_snippet(tmp_path, "broken", text)
    with pytest.raises(AttentionError) as raised:
        snippets.read(path)
    assert field in str(raised.value)
    assert "broken" in str(raised.value)


def test_malformed_yaml_names_the_snippet(tmp_path: Path) -> None:
    path = write_snippet(tmp_path, "broken", "---\ntitle: [unclosed\n---\n\nB.\n")
    with pytest.raises(AttentionError) as raised:
        snippets.read(path)
    assert "broken" in str(raised.value)


def test_an_unclosed_frontmatter_block_is_refused(tmp_path: Path) -> None:
    path = write_snippet(tmp_path, "broken", "---\ntitle: X\n\nNo closing fence.\n")
    with pytest.raises(AttentionError) as raised:
        snippets.read(path)
    assert "never closed" in str(raised.value)


def test_frontmatter_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    path = write_snippet(tmp_path, "broken", "---\n- a list\n---\n\nB.\n")
    with pytest.raises(AttentionError) as raised:
        snippets.read(path)
    assert "mapping" in str(raised.value)


def test_an_unrecognized_field_is_ignored(tmp_path: Path) -> None:
    text = "---\ntitle: X\nfuture_option: whatever\n---\n\nBody.\n"
    snippet = snippets.read(write_snippet(tmp_path, "x", text))
    assert snippet.title == "X"
    assert snippet.body == "Body.\n"


def test_a_snippet_file_is_readable_without_mdcompose(tmp_path: Path) -> None:
    """The point of the format: plain markdown, readable in any editor."""
    path = write_snippet(tmp_path, "python-style", FULL)
    raw = path.read_text(encoding="utf-8")
    assert raw.startswith("---")
    assert "Use pathlib" in raw


def test_content_is_emitted_verbatim(tmp_path: Path) -> None:
    body = "Keep {{this}} and ${that} and {0} exactly as written.\n"
    snippet = snippets.read(write_snippet(tmp_path, "literal", f"---\ntitle: L\n---\n\n{body}"))
    assert snippet.body == body


def test_no_substitution_syntax_is_reserved(tmp_path: Path) -> None:
    """Reserving nothing now is what keeps adding templating later cheap."""
    for sequence in ("{{name}}", "${name}", "%name%", "<name>", "{name}"):
        text = f"---\ntitle: T\n---\n\nvalue {sequence} here\n"
        snippet = snippets.read(write_snippet(tmp_path, "seq", text))
        assert sequence in snippet.body


def test_a_non_markdown_file_is_not_a_snippet(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not a snippet", encoding="utf-8")
    write_snippet(tmp_path, "real", BODY_ONLY)
    assert [snippet.id for snippet in snippets.load_library(tmp_path)] == ["real"]


def test_unrecognized_entries_are_skipped_without_complaint(tmp_path: Path) -> None:
    """A library kept in git must not look broken to mdcompose."""
    write_snippet(tmp_path, "real", BODY_ONLY)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "README").write_text("hello", encoding="utf-8")
    assert [snippet.id for snippet in snippets.load_library(tmp_path)] == ["real"]


def test_reading_the_library_writes_nothing(tmp_path: Path) -> None:
    write_snippet(tmp_path, "real", BODY_ONLY)
    before = sorted(path.name for path in tmp_path.iterdir())
    snippets.load_library(tmp_path)
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_writing_a_snippet_through_a_symlink_is_refused(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("not a snippet\n", encoding="utf-8")
    try:
        (library / "planted.md").symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation not permitted here")

    snippet = snippets.parse(BODY_ONLY, "planted")
    with pytest.raises(AttentionError, match="symlink"):
        snippets.write(library, snippet)
    assert outside.read_text(encoding="utf-8") == "not a snippet\n"


def test_an_absent_library_is_empty_not_an_error(tmp_path: Path) -> None:
    absent = tmp_path / "never-created"
    assert snippets.load_library(absent) == ()
    assert not absent.exists()


def test_an_empty_library_is_empty_not_an_error(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    view = snippets.view(tmp_path)
    assert view.is_empty
    assert view.snippets == ()


def test_writing_a_snippet_adds_only_that_file(tmp_path: Path) -> None:
    library = tmp_path / "library"
    snippets.write(library, snippets.Snippet(id="one", body="Body.\n"))
    assert sorted(path.name for path in library.iterdir()) == ["one.md"]


def test_writing_creates_no_index_or_cache(tmp_path: Path) -> None:
    """Any future cache belongs in the config directory, never in the library."""
    library = tmp_path / "library"
    snippets.write(library, snippets.Snippet(id="one", body="Body.\n"))
    snippets.view(library)
    snippets.write(library, snippets.Snippet(id="two", body="Body.\n"))
    assert sorted(path.name for path in library.iterdir()) == ["one.md", "two.md"]


def test_a_rendered_snippet_round_trips(tmp_path: Path) -> None:
    original = snippets.read(write_snippet(tmp_path, "python-style", FULL))
    reparsed = snippets.parse(snippets.render(original), "python-style")
    assert reparsed.body == original.body
    assert reparsed.title == original.title
    assert reparsed.tags == original.tags
    assert reparsed.order == original.order
    assert reparsed.applies_to == original.applies_to


def test_a_minimal_snippet_renders_without_a_frontmatter_block() -> None:
    """A snippet with no metadata should not grow a wall of nulls."""
    rendered = snippets.render(snippets.Snippet(id="bare", body="Body.\n"))
    assert rendered == "Body.\n"


@pytest.mark.parametrize("candidate", ["a/b", "..", "with space", "", ".hidden", "a\\b"])
def test_an_unusable_snippet_name_is_refused(candidate: str) -> None:
    with pytest.raises(AttentionError):
        snippets.validate_id(candidate)


@pytest.mark.parametrize("candidate", ["python-style", "a", "a.b", "a_b", "A1"])
def test_a_usable_snippet_name_is_accepted(candidate: str) -> None:
    assert snippets.validate_id(candidate) == candidate


def named(*specs: tuple[str, int | None]) -> list[snippets.Snippet]:
    return [
        snippets.Snippet(id=name, body=f"{name}\n", order=order) for name, order in specs
    ]


def test_ordered_snippets_come_first() -> None:
    selection = named(("unordered", None), ("first", 10))
    assert [s.id for s in snippets.compose_order(selection)] == ["first", "unordered"]


def test_ordered_snippets_sort_ascending() -> None:
    selection = named(("later", 20), ("earlier", 10))
    assert [s.id for s in snippets.compose_order(selection)] == ["earlier", "later"]


def test_a_tie_keeps_selection_order() -> None:
    selection = named(("b", 10), ("a", 10))
    assert [s.id for s in snippets.compose_order(selection)] == ["b", "a"]


def test_unordered_snippets_keep_selection_order() -> None:
    selection = named(("c", None), ("a", None), ("b", None))
    assert [s.id for s in snippets.compose_order(selection)] == ["c", "a", "b"]


def test_adding_an_order_does_not_reshuffle_the_others() -> None:
    """Unordered snippets sort last rather than at a default value, so adding an
    order to one snippet cannot silently rearrange every other snippet."""
    before = named(("a", None), ("b", None), ("c", None))
    after = named(("a", None), ("b", None), ("c", 5))
    assert [s.id for s in snippets.compose_order(before)] == ["a", "b", "c"]
    assert [s.id for s in snippets.compose_order(after)] == ["c", "a", "b"]
    unordered_before = [s.id for s in snippets.compose_order(before) if s.order is None]
    unordered_after = [s.id for s in snippets.compose_order(after) if s.order is None]
    assert unordered_after == [name for name in unordered_before if name != "c"]


def test_filters_narrow_rather_than_widen(tmp_path: Path) -> None:
    write_snippet(tmp_path, "one", "---\ntags: [python]\ncategory: conventions\n---\n\nB.\n")
    write_snippet(tmp_path, "two", "---\ntags: [python]\ncategory: testing\n---\n\nB.\n")
    write_snippet(tmp_path, "three", "---\ntags: [go]\ncategory: conventions\n---\n\nB.\n")
    library = snippets.load_library(tmp_path)

    by_tag = snippets.filter_snippets(library, tag="python")
    by_category = snippets.filter_snippets(library, category="conventions")
    by_both = snippets.filter_snippets(library, tag="python", category="conventions")

    assert {s.id for s in by_tag} == {"one", "two"}
    assert {s.id for s in by_category} == {"one", "three"}
    assert {s.id for s in by_both} == {"one"}
    assert len(by_both) <= min(len(by_tag), len(by_category))


def test_a_filter_matching_nothing_returns_nothing(tmp_path: Path) -> None:
    write_snippet(tmp_path, "one", "---\ntags: [python]\n---\n\nB.\n")
    assert snippets.filter_snippets(snippets.load_library(tmp_path), tag="rust") == ()


def test_requiring_an_unknown_id_names_it(tmp_path: Path) -> None:
    view = snippets.view(tmp_path)
    with pytest.raises(AttentionError) as raised:
        view.require("absent")
    assert "absent" in str(raised.value)


def test_a_snippet_with_a_bom_reads_the_same(tmp_path: Path) -> None:
    path = tmp_path / "x.md"
    tmp_path.mkdir(exist_ok=True)
    path.write_bytes((files.BOM + FULL).encode("utf-8"))
    assert snippets.read(path).title == "Python style"


def test_a_snippet_with_crlf_reads_the_same(tmp_path: Path) -> None:
    path = tmp_path / "x.md"
    tmp_path.mkdir(exist_ok=True)
    path.write_bytes(FULL.replace("\n", "\r\n").encode("utf-8"))
    snippet = snippets.read(path)
    assert snippet.title == "Python style"
    assert snippet.body == "Use pathlib. Always specify encoding.\n"
