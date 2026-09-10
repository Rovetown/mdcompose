"""The mdcompose command line interface.

A thin adapter over the core layer. Commands parse arguments, call core, and
format the result. No detection, path resolution, encoding, or config logic
lives here, which is what lets the core behavior be documented as a contract
independent of Python and of Typer.

Rich markup is disabled deliberately. Its help output draws boxes with Unicode
characters, which would break the plain-ASCII guarantee that exists so a legacy
Windows console cannot raise an encoding error.
"""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path
from typing import Annotated

import typer

from mdcompose.commands import (
    config_cmd,
    convert_cmd,
    eject_cmd,
    import_cmd,
    init_cmd,
    snippet_cmd,
    target_cmd,
)
from mdcompose.core import report as report_module
from mdcompose.core.exit_codes import EXIT_ATTENTION, EXIT_INTERNAL, EXIT_OK, AttentionError
from mdcompose.core.output import GlobalOptions, OutputContext, assert_ascii
from mdcompose.prompts import output_for

PACKAGE_NAME = "mdcompose"

app = typer.Typer(
    name=PACKAGE_NAME,
    help="Manage CLAUDE.md and AGENTS.md, and compose them from a personal snippet library.",
    rich_markup_mode=None,
    add_completion=False,
)


def resolve_version() -> str:
    """Return the installed version, the same string recorded in a manifest.

    Falls back to a marker rather than raising when package metadata is
    unavailable, which happens only in a source tree that was never installed.
    """
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return "0+unknown"


def _version_callback(requested: bool) -> None:
    if not requested:
        return
    print(assert_ascii(resolve_version()), file=sys.stdout)
    raise typer.Exit(EXIT_OK)


QuietOption = Annotated[
    bool,
    typer.Option("--quiet", "-q", help="Suppress informational output. Errors still print."),
]
JsonOption = Annotated[
    bool,
    typer.Option("--json", help="Emit one JSON document on stdout and nothing else."),
]
NoColourOption = Annotated[
    bool,
    typer.Option("--no-color", help="Never colourize output."),
]
VersionOption = Annotated[
    bool,
    typer.Option(
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
]


@app.callback()
def main(
    context: typer.Context,
    quiet: QuietOption = False,
    json_output: JsonOption = False,
    no_colour: NoColourOption = False,
    _version: VersionOption = False,
) -> None:
    """Record the flags every command shares on the Typer context."""
    context.obj = GlobalOptions(quiet=quiet, json_mode=json_output, no_colour=no_colour)


app.add_typer(snippet_cmd.app, name="snippet")
app.add_typer(config_cmd.app, name="config")
app.add_typer(target_cmd.app, name="target")
init_cmd.register(app)
import_cmd.register(app)
convert_cmd.register(app)
eject_cmd.register(app)


@app.command()
def doctor(
    context: typer.Context,
    quiet: QuietOption = False,
    json_output: JsonOption = False,
    no_colour: NoColourOption = False,
) -> None:
    """Report the detected platform and every path mdcompose resolves.

    Creates nothing, modifies nothing, and never prompts, so it is safe to run
    anywhere. Exits 0 when healthy and 1 when something needs attention, which
    makes it usable as a CI gate without parsing its output.
    """
    output = output_for(
        context, quiet=quiet, json_output=json_output, no_colour=no_colour
    )
    report = report_module.build_doctor_report(project_root=Path.cwd())

    for warning in report.warnings:
        output.warn(warning)

    if output.json_mode:
        output.emit(report.to_json())
    else:
        render_doctor(output, report)

    if report.needs_attention:
        raise typer.Exit(EXIT_ATTENTION)


def render_doctor(output: OutputContext, report: report_module.DoctorReport) -> None:
    """Format the report for a person reading a terminal.

    Every status is readable from the text, so nothing depends on colour, and
    the columns align because every generated character is ASCII.
    """
    output.info(output.bold("platform"))
    output.info(f"  os   {report.os_name}")
    output.info(f"  wsl  {'yes' if report.is_wsl else 'no'}")
    output.info("")
    output.info(output.bold("paths"))

    label_width = max(len(entry.label) for entry in report.entries)
    status_width = max(len(entry.status) for entry in report.entries)
    for entry in report.entries:
        location = "-" if entry.resolved is None else entry.resolved.path.as_posix()
        label = entry.label.ljust(label_width)
        status = entry.status.ljust(status_width)
        output.info(f"  {label}  {status}  {location}")

    if report.targets:
        output.info("")
        output.info(output.bold("registered targets"))
        label_width = max(len(target.label) for target in report.targets)
        for target in report.targets:
            present = "present" if target.present else "absent"
            output.info(
                f"  {target.label.ljust(label_width)}  {target.sync:12}  {present}  {target.path}"
            )

    output.info("")
    output.info(output.bold("managed files"))
    if report.drift is None:
        output.info("  not initialized, mdcompose has not composed this directory")
        return
    if not report.drift:
        output.info("  the manifest records no managed files")
        return
    key_width = max(len(drift.key) for drift in report.drift)
    for drift in report.drift:
        detail = "" if drift.detail is None else f"  ({drift.detail})"
        output.info(f"  {drift.key.ljust(key_width)}  {drift.status}{detail}")


def run(argv: list[str] | None = None) -> int:
    """The single error boundary. Every exception becomes an exit code here.

    ``AttentionError`` means mdcompose worked and is reporting a real condition
    the user must resolve, so it exits 1 with the message on stderr. A usage
    error or an unexpected exception means mdcompose could not do its job, so
    both exit 2.

    Typer 0.27 vendors Click as a private module, so the usage error family is
    caught through the public ``typer.TyperException``, which every vendored
    Click exception inherits from.

    A command signals a non-zero outcome by raising ``typer.Exit``. Outside
    standalone mode Typer does not let that propagate; it converts it into the
    value ``app`` returns. So the return value is the exit code, and ignoring it
    would silently turn every non-zero outcome into success.

    ``argv`` defaults to the real command line. Tests pass it explicitly so the
    boundary itself is exercised rather than bypassed.

    A bare invocation shows help and succeeds. Running mdcompose with no
    arguments is not mdcompose failing, so it does not earn exit code 2.
    """
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        arguments = ["--help"]
    try:
        result = app(args=arguments, prog_name=PACKAGE_NAME, standalone_mode=False)
    except AttentionError as error:
        print(assert_ascii(f"error: {error.message}"), file=sys.stderr)
        return EXIT_ATTENTION
    except typer.Exit as request:
        return request.exit_code
    except typer.Abort:
        print("error: aborted", file=sys.stderr)
        return EXIT_ATTENTION
    except typer.TyperException as error:
        show = getattr(error, "show", None)
        if show is None:
            print(f"error: {error}", file=sys.stderr)
        else:
            show()
        return EXIT_INTERNAL
    except Exception as error:  # the boundary must catch everything
        print(
            f"error: mdcompose failed unexpectedly ({type(error).__name__}: {error}). "
            "This is a bug in mdcompose.",
            file=sys.stderr,
        )
        return EXIT_INTERNAL
    return EXIT_OK if result is None else int(result)
