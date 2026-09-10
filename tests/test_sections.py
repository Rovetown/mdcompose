"""Heading-based section extraction: boundaries, levels, fences, keyword filter."""

from __future__ import annotations

from mdcompose.core import sections
from mdcompose.core.files import normalize

NESTED = """\
Intro line.

# Top

Top body.

## Alpha

Alpha body.

## Beta

Beta body.

### Beta child

Child body.

# Second

Second body.
"""


def parse(text: str, name: str = "SOURCE.md") -> tuple[sections.Section, ...]:
    return sections.parse_sections(text, source_name=name)


def by_heading(text: str, heading: str) -> sections.Section:
    found = next(s for s in parse(text) if s.heading == heading)
    return found


# 1.1 fence-aware scanning


def test_a_heading_inside_a_fenced_block_is_not_a_boundary() -> None:
    text = "# Real\n\n```\n# Not a heading\n```\n\nStill under Real.\n"
    result = parse(text)
    assert [s.heading for s in result] == ["Real"]
    assert "# Not a heading" in result[0].content
    assert "Still under Real." in result[0].content


def test_a_tilde_fence_also_hides_headings() -> None:
    text = "# Real\n\n~~~markdown\n## Fake\n~~~\n\ntail\n"
    assert [s.heading for s in parse(text)] == ["Real"]


# 1.2 section boundaries


def test_a_section_runs_to_the_next_same_or_higher_heading() -> None:
    top = by_heading(NESTED, "Top")
    assert "Alpha body." in top.content
    assert "Beta child" in top.content
    assert "Second body." not in top.content


def test_a_sibling_heading_ends_the_section() -> None:
    alpha = by_heading(NESTED, "Alpha")
    assert alpha.content.strip().endswith("Alpha body.")
    assert "Beta" not in alpha.content


def test_the_last_heading_extends_to_end_of_file() -> None:
    second = by_heading(NESTED, "Second")
    assert second.content.endswith("Second body.\n")


def test_a_subsection_stops_at_its_parents_sibling() -> None:
    child = by_heading(NESTED, "Beta child")
    assert "Child body." in child.content
    assert "Second" not in child.content


# 1.3 content before the first heading


def test_content_before_the_first_heading_is_kept_as_a_section() -> None:
    preamble = parse(NESTED)[0]
    assert preamble.synthetic
    assert preamble.heading == "SOURCE.md"
    assert "Intro line." in preamble.content


def test_a_file_that_starts_with_a_heading_has_no_preamble_section() -> None:
    result = parse("# Only\n\nbody\n")
    assert [s.heading for s in result] == ["Only"]


# 1.4 no headings


def test_a_file_with_no_headings_is_one_section() -> None:
    result = parse("Just prose.\n\nMore prose.\n")
    assert len(result) == 1
    assert result[0].synthetic
    assert result[0].heading == "SOURCE.md"
    assert result[0].content == "Just prose.\n\nMore prose.\n"


# 1.5 verbatim round trip


def test_maximal_sections_reassemble_into_the_source() -> None:
    result = parse(NESTED)
    maximal = sections.maximal(result)
    assert "".join(s.content for s in maximal) == normalize(NESTED)


def test_round_trip_holds_with_crlf_and_no_trailing_newline() -> None:
    text = "# A\r\nbody\r\n\r\n## B\r\nmore"
    result = parse(text)
    assert "".join(s.content for s in sections.maximal(result)) == normalize(text)


# 1.6 every level enumerated


def test_a_parent_and_both_children_are_all_offered() -> None:
    text = "## Parent\n\np\n\n### One\n\n1\n\n### Two\n\n2\n"
    result = parse(text)
    assert [(s.heading, s.level) for s in result] == [
        ("Parent", 2),
        ("One", 3),
        ("Two", 3),
    ]


# 1.7 subsection extracted alone


def test_selecting_a_subsection_extracts_only_it() -> None:
    child = by_heading(NESTED, "Beta child")
    extracted = sections.extract([child])
    assert extracted == child.content
    assert extracted.startswith("### Beta child")
    assert "Beta body." not in extracted


def test_selecting_a_parent_includes_its_children() -> None:
    beta = by_heading(NESTED, "Beta")
    extracted = sections.extract([beta])
    assert "Beta child" in extracted
    assert "Child body." in extracted


# 1.8 de-duplication


def test_selecting_a_parent_and_a_child_applies_the_content_once() -> None:
    beta = by_heading(NESTED, "Beta")
    child = by_heading(NESTED, "Beta child")
    extracted = sections.extract([beta, child])
    assert extracted.count("Child body.") == 1
    assert extracted == beta.content


def test_extract_orders_by_position_in_the_source() -> None:
    top = by_heading(NESTED, "Top")
    second = by_heading(NESTED, "Second")
    assert sections.extract([second, top]) == top.content + second.content


# 1.9 keyword filter


def test_a_keyword_narrows_to_matching_sections() -> None:
    text = "# Testing\n\npytest and coverage\n\n# Build\n\nhatchling\n"
    matched = sections.filter_by_keyword(parse(text), "pytest")
    assert [s.heading for s in matched] == ["Testing"]


def test_the_keyword_match_is_case_insensitive() -> None:
    text = "# Testing\n\nPyTest\n"
    assert sections.filter_by_keyword(parse(text), "pytest")


def test_a_parent_surfaces_when_only_its_child_matches() -> None:
    text = "## Parent\n\ngeneric\n\n### Child\n\nthe pytest bit\n"
    matched = sections.filter_by_keyword(parse(text), "pytest")
    assert {s.heading for s in matched} == {"Parent", "Child"}


def test_a_keyword_can_match_the_heading_itself() -> None:
    text = "# Deployment notes\n\nbody\n\n# Other\n\nbody\n"
    matched = sections.filter_by_keyword(parse(text), "deployment")
    assert [s.heading for s in matched] == ["Deployment notes"]


# 1.10 filter does not change granularity


def test_a_filtered_section_still_extracts_whole() -> None:
    text = "## Parent\n\ngeneric\n\n### Child\n\nthe pytest bit\n"
    matched = sections.filter_by_keyword(parse(text), "pytest")
    child = next(s for s in matched if s.heading == "Child")
    assert sections.extract([child]) == child.content
    assert "the pytest bit" in sections.extract([child])


def test_no_match_returns_an_empty_tuple() -> None:
    text = "# A\n\nbody\n"
    assert sections.filter_by_keyword(parse(text), "absent") == ()


# heading text normalization


def test_a_closing_hash_sequence_is_not_part_of_the_heading_text() -> None:
    assert by_heading("## Framed ##\n\nbody\n", "Framed").level == 2


def test_up_to_three_leading_spaces_still_makes_a_heading() -> None:
    assert [s.heading for s in parse("   # Indented\n\nbody\n")] == ["Indented"]


def test_four_leading_spaces_is_a_code_line_not_a_heading() -> None:
    result = parse("Prose.\n\n    # Not a heading\n")
    assert len(result) == 1
    assert result[0].synthetic
