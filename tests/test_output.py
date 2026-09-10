"""Stream discipline, colour, quiet mode, and the plain-ASCII guarantee."""

from __future__ import annotations

import io

import pytest
from conftest import make_output

from mdcompose.core.output import (
    GlobalOptions,
    NonAsciiOutputError,
    assert_ascii,
    build_output_context,
)

NON_ASCII_SAMPLES = [
    "an em dash \u2014 here",
    "an arrow \u2192",
    "an emoji \U0001f600",
    "a\u00a0nbsp",
]


def test_information_goes_to_stdout() -> None:
    captured = make_output()
    captured.context.info("the report")
    assert captured.out.getvalue() == "the report\n"
    assert captured.err.getvalue() == ""


def test_warnings_go_to_stderr() -> None:
    captured = make_output()
    captured.context.warn("something to know")
    assert captured.out.getvalue() == ""
    assert "something to know" in captured.err.getvalue()


def test_errors_go_to_stderr() -> None:
    captured = make_output()
    captured.context.error("something wrong")
    assert captured.out.getvalue() == ""
    assert "something wrong" in captured.err.getvalue()


def test_redirecting_stdout_keeps_warnings_visible() -> None:
    """Warnings survive a caller that only captures stdout."""
    captured = make_output()
    captured.context.info("report body")
    captured.context.warn("still visible")
    assert "still visible" not in captured.out.getvalue()
    assert "still visible" in captured.err.getvalue()


def test_quiet_suppresses_information() -> None:
    captured = make_output(quiet=True)
    captured.context.info("noise")
    assert captured.out.getvalue() == ""


def test_quiet_never_suppresses_warnings_or_errors() -> None:
    captured = make_output(quiet=True)
    captured.context.warn("a warning")
    captured.context.error("an error")
    combined = captured.err.getvalue()
    assert "a warning" in combined
    assert "an error" in combined


def test_quiet_never_suppresses_requested_output() -> None:
    """A document the caller asked for by name is not informational."""
    captured = make_output(quiet=True, json_mode=True)
    captured.context.emit('{"asked": "for"}')
    assert captured.out.getvalue() == '{"asked": "for"}\n'


@pytest.mark.parametrize("sample", NON_ASCII_SAMPLES)
def test_generated_output_must_be_ascii(sample: str) -> None:
    with pytest.raises(NonAsciiOutputError) as raised:
        assert_ascii(sample)
    assert "U+" in str(raised.value)


def test_ascii_text_passes_through_unchanged() -> None:
    plain = "plain ascii, with punctuation: fine."
    assert assert_ascii(plain) == plain


@pytest.mark.parametrize("sample", NON_ASCII_SAMPLES)
def test_every_emitting_method_refuses_non_ascii(sample: str) -> None:
    captured = make_output()
    methods = (
        captured.context.info,
        captured.context.emit,
        captured.context.warn,
        captured.context.error,
    )
    for method in methods:
        with pytest.raises(NonAsciiOutputError):
            method(sample)


def test_transported_content_is_not_restricted() -> None:
    """Content mdcompose carries is the user's, and passes through unaltered."""
    body = "A snippet with an em dash \u2014 and an emoji \U0001f600.\n"
    captured = make_output()
    captured.context.content(body)
    assert captured.out.getvalue() == body + "\n"


def test_content_indented_prefixes_four_spaces() -> None:
    captured = make_output()
    captured.context.content_indented("first\nsecond\n")
    assert captured.out.getvalue() == "    first\n    second\n"


def test_content_indented_shows_the_empty_placeholder_for_blank_content() -> None:
    captured = make_output()
    captured.context.content_indented("   \n", empty="    (empty)")
    assert captured.out.getvalue() == "    (empty)\n"


def test_generated_output_encodes_on_a_legacy_windows_code_page() -> None:
    """The whole point of the ASCII rule: cp1252 must never raise."""
    captured = make_output()
    captured.context.info("os   windows")
    captured.context.warn("a path is on a Windows drive mounted under /mnt/")
    for text in (captured.out.getvalue(), captured.err.getvalue()):
        assert text.encode("cp1252").decode("cp1252") == text
        assert text.encode("cp437").decode("cp437") == text


def test_colour_is_off_when_not_a_terminal() -> None:
    context = build_output_context(environ={}, out=io.StringIO(), err=io.StringIO())
    assert context.colour is False
    assert context.bold("label") == "label"


def test_colour_is_off_when_no_color_is_set() -> None:
    stream = io.StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    context = build_output_context(environ={"NO_COLOR": "1"}, out=stream, err=io.StringIO())
    assert context.colour is False


def test_colour_is_off_when_asked_explicitly() -> None:
    stream = io.StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    context = build_output_context(no_colour=True, environ={}, out=stream, err=io.StringIO())
    assert context.colour is False


def test_colour_is_off_in_json_mode() -> None:
    stream = io.StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    context = build_output_context(json_mode=True, environ={}, out=stream, err=io.StringIO())
    assert context.colour is False


def test_colour_is_on_for_a_plain_terminal() -> None:
    stream = io.StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    context = build_output_context(environ={}, out=stream, err=io.StringIO())
    assert context.colour is True
    assert context.bold("label") != "label"


def test_colour_never_carries_meaning_alone() -> None:
    """Whatever a decoration says, the plain text says the same thing."""
    stream = io.StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    coloured = build_output_context(environ={}, out=stream, err=io.StringIO())
    plain = build_output_context(no_colour=True, environ={}, out=io.StringIO(), err=io.StringIO())
    for text in ("platform", "paths"):
        assert text in coloured.bold(text)
        assert plain.bold(text) == text


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (GlobalOptions(), GlobalOptions(quiet=True), GlobalOptions(quiet=True)),
        (GlobalOptions(json_mode=True), GlobalOptions(), GlobalOptions(json_mode=True)),
        (GlobalOptions(quiet=True), GlobalOptions(quiet=True), GlobalOptions(quiet=True)),
        (GlobalOptions(), GlobalOptions(), GlobalOptions()),
    ],
)
def test_flags_merge_as_an_or(
    first: GlobalOptions, second: GlobalOptions, expected: GlobalOptions
) -> None:
    """A flag set in either position turns it on, so positions cannot conflict."""
    assert first.merge(second) == expected
