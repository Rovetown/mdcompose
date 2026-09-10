"""Output discipline: streams, colour, quiet mode, and the ASCII guarantee.

Requested output goes to stdout. Errors, warnings, and prompts go to stderr, so
redirecting stdout to a file never hides a warning and an interactive run stays
pipeable.

Every character mdcompose generates itself is ASCII. This is an encoding
decision rather than a style preference: a Windows console on a cp1252 or cp437
code page cannot encode an emoji or an em dash, so emitting one raises
UnicodeEncodeError on a platform this project treats as primary. Emoji also have
ambiguous terminal width, which breaks column alignment in a report, and screen
readers announce them verbatim.

The rule constrains what mdcompose authors, never what it carries. A snippet body
full of emoji is the user's content and passes through unaltered, which is why
:meth:`OutputContext.content` exists alongside :meth:`OutputContext.info`.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TextIO

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


class NonAsciiOutputError(AssertionError):
    """mdcompose tried to generate a character it is not allowed to emit.

    A programming error rather than a user-facing condition, so it surfaces at
    the CLI boundary as exit code 2. Raising here is strictly better than
    letting a legacy Windows console raise UnicodeEncodeError, because this
    names the offending characters.
    """


def assert_ascii(text: str) -> str:
    """Return text unchanged, or raise if it contains a non-ASCII character."""
    if text.isascii():
        return text
    offenders = sorted({character for character in text if not character.isascii()})
    listed = ", ".join(f"U+{ord(character):04X}" for character in offenders)
    raise NonAsciiOutputError(
        f"mdcompose generated non-ASCII output ({listed}); "
        "generated text must be plain ASCII"
    )


@dataclass(frozen=True, slots=True)
class OutputContext:
    """Where output goes and how it is decorated.

    Construct with :func:`build_output_context` rather than directly, so stream
    and colour decisions are made at call time rather than at import time.
    """

    json_mode: bool
    quiet: bool
    colour: bool
    out: TextIO
    err: TextIO

    def info(self, text: str = "") -> None:
        """Write informational output to stdout, unless quiet mode is on.

        A report is informational: ``--quiet`` reduces a command to its exit
        code, which is what a CI gate wants.
        """
        if self.quiet:
            return
        print(assert_ascii(text), file=self.out)

    def emit(self, text: str) -> None:
        """Write explicitly requested output to stdout, never suppressed.

        Used for the JSON document, which the caller asked for by name and
        which must be the only thing on stdout.
        """
        print(assert_ascii(text), file=self.out)

    def content(self, text: str) -> None:
        """Write transported content to stdout without the ASCII restriction.

        For content mdcompose carries rather than authors, such as a snippet
        body or an extracted section shown in a diff.
        """
        print(text, file=self.out)

    def warn(self, text: str) -> None:
        """Write a warning to stderr. Never suppressed by quiet mode."""
        print(assert_ascii(f"warning: {text}"), file=self.err)

    def error(self, text: str) -> None:
        """Write an error to stderr. Never suppressed by quiet mode."""
        print(assert_ascii(f"error: {text}"), file=self.err)

    def bold(self, text: str) -> str:
        """Return text emphasized, or unchanged when colour is off.

        Emphasis never carries meaning on its own; the plain text always says
        the same thing.
        """
        if not self.colour:
            return text
        return f"{_BOLD}{text}{_RESET}"

    def dim(self, text: str) -> str:
        """Return text de-emphasized, or unchanged when colour is off."""
        if not self.colour:
            return text
        return f"{_DIM}{text}{_RESET}"


@dataclass(frozen=True, slots=True)
class GlobalOptions:
    """The flags every command accepts, before streams are decided.

    These are accepted both before a command name and after it, because a user
    types ``mdcompose doctor --json`` at least as often as
    ``mdcompose --json doctor``. Merging is an OR: setting a flag in either
    position turns it on, so the two positions cannot contradict each other.
    """

    quiet: bool = False
    json_mode: bool = False
    no_colour: bool = False

    def merge(self, other: GlobalOptions) -> GlobalOptions:
        """Combine two sets of flags, taking a flag as set if either sets it."""
        return GlobalOptions(
            quiet=self.quiet or other.quiet,
            json_mode=self.json_mode or other.json_mode,
            no_colour=self.no_colour or other.no_colour,
        )


def build_output_context(
    *,
    json_mode: bool = False,
    quiet: bool = False,
    no_colour: bool = False,
    environ: Mapping[str, str] | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> OutputContext:
    """Decide streams and colour for one command invocation."""
    stream_out = sys.stdout if out is None else out
    stream_err = sys.stderr if err is None else err
    return OutputContext(
        json_mode=json_mode,
        quiet=quiet,
        colour=_colour_enabled(
            json_mode=json_mode,
            no_colour=no_colour,
            environ=environ,
            out=stream_out,
        ),
        out=stream_out,
        err=stream_err,
    )


def _colour_enabled(
    *,
    json_mode: bool,
    no_colour: bool,
    environ: Mapping[str, str] | None,
    out: TextIO,
) -> bool:
    """Return whether to colourize, honouring every way to say no.

    Colour is off unless stdout is a terminal, and off regardless when the user
    or the environment asks for it to be off, or when the output is a machine
    readable document.
    """
    if no_colour or json_mode:
        return False
    variables = os_environ() if environ is None else environ
    if "NO_COLOR" in variables:
        return False
    isatty = getattr(out, "isatty", None)
    return bool(isatty is not None and isatty())


def os_environ() -> Mapping[str, str]:
    """Return the process environment.

    A function rather than a module-level binding, so nothing is captured at
    import time and tests can substitute a mapping instead.
    """
    return os.environ
