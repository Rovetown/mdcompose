"""Shared test fixtures and helpers."""

from __future__ import annotations

import io
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from mdcompose import cli
from mdcompose.core.output import GlobalOptions, OutputContext, build_output_context
from mdcompose.core.platform import PlatformInfo

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass(frozen=True, slots=True)
class Invocation:
    """The full observable result of running mdcompose once."""

    code: int
    out: str
    err: str


@pytest.fixture
def invoke(capsys: pytest.CaptureFixture[str]) -> Callable[..., Invocation]:
    """Run mdcompose through its real error boundary and capture everything.

    Goes through ``cli.run`` rather than a test runner, so the exit code under
    test is the one a shell would actually see.
    """

    def _invoke(*args: str) -> Invocation:
        code = cli.run(list(args))
        captured = capsys.readouterr()
        return Invocation(code=code, out=captured.out, err=captured.err)

    return _invoke


@pytest.fixture
def windows() -> PlatformInfo:
    return PlatformInfo(os_name="windows", is_wsl=False)


@pytest.fixture
def linux() -> PlatformInfo:
    return PlatformInfo(os_name="linux", is_wsl=False)


@pytest.fixture
def wsl() -> PlatformInfo:
    return PlatformInfo(os_name="linux", is_wsl=True)


@dataclass(frozen=True, slots=True)
class CapturedOutput:
    """An OutputContext writing into buffers a test can read back."""

    context: OutputContext
    out: io.StringIO
    err: io.StringIO


def make_output(
    *,
    quiet: bool = False,
    json_mode: bool = False,
    no_colour: bool = True,
    environ: Mapping[str, str] | None = None,
) -> CapturedOutput:
    """Build an OutputContext over string buffers instead of the real streams."""
    out = io.StringIO()
    err = io.StringIO()
    context = build_output_context(
        json_mode=json_mode,
        quiet=quiet,
        no_colour=no_colour,
        environ={} if environ is None else environ,
        out=out,
        err=err,
    )
    return CapturedOutput(context=context, out=out, err=err)


def options(**kwargs: bool) -> GlobalOptions:
    """Build GlobalOptions with only the named flags set."""
    return GlobalOptions(**kwargs)
