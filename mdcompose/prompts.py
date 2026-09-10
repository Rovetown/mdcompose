"""CLI-layer helpers shared by every command: output wiring and prompting.

These sit at the CLI layer rather than in core, because prompting is
presentation. They live in their own module rather than in `cli.py` so a command
module can use them without importing the app that registers it.

Every prompt here takes the answer as an optional argument. Supplying it skips
the question, which is how the guarantee that every prompt has a flag is kept
mechanically rather than by discipline.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

import typer

from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.output import GlobalOptions, OutputContext, build_output_context


def output_for(
    context: typer.Context,
    *,
    quiet: bool = False,
    json_output: bool = False,
    no_colour: bool = False,
) -> OutputContext:
    """Build the output context for a command, merging both flag positions.

    A flag may be given before the command name or after it. Merging is an OR,
    so the two positions cannot contradict each other.
    """
    base = context.obj if isinstance(context.obj, GlobalOptions) else GlobalOptions()
    merged = base.merge(
        GlobalOptions(quiet=quiet, json_mode=json_output, no_colour=no_colour)
    )
    return build_output_context(
        json_mode=merged.json_mode,
        quiet=merged.quiet,
        no_colour=merged.no_colour,
    )


def is_interactive() -> bool:
    """Whether there is a terminal to ask a question on."""
    isatty = getattr(sys.stdin, "isatty", None)
    return bool(isatty is not None and isatty())


def confirm(
    output: OutputContext,
    question: str,
    *,
    assume_yes: bool = False,
    flag: str = "--yes",
) -> bool:
    """Ask a yes or no question, unless the answer was supplied.

    Refuses to guess when there is nobody to ask, naming the flag that would
    have answered it. A machine-readable run never prompts either, because output
    that looks authoritative while answering a different question is worse than a
    refusal.
    """
    if assume_yes:
        return True
    if output.json_mode or not is_interactive():
        raise AttentionError(
            f"{question} No answer was supplied and there is no terminal to ask on. "
            f"Pass {flag} to answer it."
        )
    return typer.confirm(question, default=False, err=True)


def prompt_choice(
    output: OutputContext,
    subject: str,
    *,
    options: Sequence[str],
    default: str,
    flag: str,
) -> str:
    """Ask the user to pick one of several named options.

    Same rule as `confirm`: with no terminal and no flag, this refuses rather
    than quietly taking the default.
    """
    if output.json_mode or not is_interactive():
        raise AttentionError(
            f"{subject} needs a decision and there is no terminal to ask on. "
            f"Pass {flag} with one of: {', '.join(options)}."
        )
    listed = ", ".join(options)
    answer: str = typer.prompt(
        f"{subject}: {listed}",
        default=default,
        err=True,
    ).strip()
    if answer not in options:
        raise AttentionError(f"'{answer}' is not one of: {listed}")
    return answer
