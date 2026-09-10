"""Property tests for the two parsers that read arbitrary markdown.

`sections.parse_sections` and `managed_block.scan` are the only functions that
run over content a user or a repository hands in without mdcompose having
written it. Both must be total: any string in, a well-formed result out, no
unhandled exception and no runaway loop. These tests assert that invariant
against generated input, including input shaped to look like markers, fences,
and headings.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from mdcompose.core import managed_block, sections
from mdcompose.core.files import normalize

MARKER_PREFIX = managed_block.MARKER_PREFIX

#: Lines chosen to stress the heading, fence, and marker recognisers.
_STRESS_LINES = st.sampled_from(
    [
        "",
        "#",
        "###### deep heading",
        "#" * 40 + " absurd heading",
        "```",
        "```python",
        "~~~",
        "   ```   ",
        f"<!-- {MARKER_PREFIX}:agents-composition:start -->",
        f"<!-- {MARKER_PREFIX}:agents-composition:end -->",
        f"<!-- {MARKER_PREFIX}:claude-managed:start -->",
        f"<!--{MARKER_PREFIX}:x:start-->",
        "<!-- mdcompose:UPPER:start -->",
        "<!-- not a marker -->",
        "\r",
        "text\twith\ttabs",
        "trailing space   ",
        "a" * 500,
    ]
)

_MARKUP_TEXT = st.lists(st.one_of(_STRESS_LINES, st.text(max_size=80)), max_size=60).map(
    "\n".join
)

_ANY_TEXT = st.one_of(
    st.text(),
    _MARKUP_TEXT,
    st.text(alphabet=st.characters(min_codepoint=0, max_codepoint=0x2FFF)),
)


@settings(max_examples=400, deadline=1000)
@given(_ANY_TEXT)
def test_parse_sections_is_total(text: str) -> None:
    result = sections.parse_sections(text, source_name="fuzz.md")
    assert isinstance(result, tuple)
    line_count = max(1, len(normalize(text).split("\n")))
    for section in result:
        assert 1 <= section.start_line <= section.end_line <= line_count
    # The concatenation of what was found still parses without raising or looping.
    sections.parse_sections(sections.extract(result), source_name="again.md")


@settings(max_examples=400, deadline=1000)
@given(_ANY_TEXT)
def test_managed_block_scan_is_total(text: str) -> None:
    result = managed_block.scan(text)
    assert isinstance(result.blocks, tuple)
    for block in result.blocks:
        assert block.start_line <= block.end_line
    if result.problem is not None:
        assert result.problem.message
        assert result.problem.kind in {
            "unmatched-start",
            "unmatched-end",
            "duplicate-id",
            "nested",
        }
