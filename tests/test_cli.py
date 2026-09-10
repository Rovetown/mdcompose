"""The CLI surface: exit codes, version, help, streams, and the doctor command.

Every test here goes through ``cli.run``, so the exit code asserted is the one a
shell would actually see and the error boundary is exercised rather than
bypassed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib import metadata
from pathlib import Path

import pytest
import typer
from conftest import Invocation

from mdcompose import cli
from mdcompose.core import config as config_module
from mdcompose.core import platform as platform_module
from mdcompose.core import report as report_module
from mdcompose.core.exit_codes import EXIT_ATTENTION, EXIT_INTERNAL, EXIT_OK
from mdcompose.core.output import NonAsciiOutputError
from mdcompose.core.platform import ResolvedPath

Invoke = Callable[..., Invocation]


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run inside an empty project with an empty config directory.

    Keeps every test off the real machine, so no test can read or disturb the
    snippet library of whoever is running the suite.
    """
    project = tmp_path / "project"
    project.mkdir()
    config_directory = tmp_path / "config"
    monkeypatch.setattr(platform_module, "config_dir", lambda: config_directory)
    monkeypatch.chdir(project)
    return config_directory


def test_version_matches_the_installed_metadata(invoke: Invoke) -> None:
    result = invoke("--version")
    assert result.code == EXIT_OK
    assert result.out.strip() == metadata.version("mdcompose")


def test_version_is_the_string_recorded_in_a_manifest(invoke: Invoke) -> None:
    """generated_by must be able to name exactly what the version flag prints."""
    result = invoke("--version")
    assert result.out.strip() == cli.resolve_version()


def test_top_level_help_lists_every_command(invoke: Invoke) -> None:
    result = invoke("--help")
    assert result.code == EXIT_OK
    assert "doctor" in result.out
    assert "mdcompose" in result.out


def test_command_help_lists_its_flags(invoke: Invoke) -> None:
    result = invoke("doctor", "--help")
    assert result.code == EXIT_OK
    for flag in ("--json", "--quiet", "--no-color"):
        assert flag in result.out


@pytest.mark.parametrize("args", [("--help",), ("doctor", "--help")])
def test_help_output_is_ascii(invoke: Invoke, args: tuple[str, ...]) -> None:
    """Rich help draws Unicode boxes, so rich markup must stay disabled."""
    assert invoke(*args).out.isascii()


def test_no_arguments_shows_help_and_succeeds(invoke: Invoke) -> None:
    """A bare invocation is not mdcompose failing, so it must not exit 2."""
    result = invoke()
    assert result.code == EXIT_OK
    assert "doctor" in result.out


def test_an_unknown_option_means_mdcompose_was_driven_wrongly(invoke: Invoke) -> None:
    assert invoke("doctor", "--nonsense").code == EXIT_INTERNAL


def test_an_unknown_command_is_a_usage_error(invoke: Invoke) -> None:
    assert invoke("summon").code == EXIT_INTERNAL


def test_doctor_reports_and_succeeds(invoke: Invoke, isolated: Path) -> None:
    result = invoke("doctor")
    assert result.code == EXIT_OK
    assert "platform" in result.out
    assert "project mdcompose.lock" in result.out


def test_doctor_output_goes_to_stdout(invoke: Invoke, isolated: Path) -> None:
    result = invoke("doctor")
    assert result.err == ""
    assert result.out != ""


def test_doctor_output_is_ascii(invoke: Invoke, isolated: Path) -> None:
    assert invoke("doctor").out.isascii()


def test_doctor_output_encodes_on_a_legacy_windows_code_page(
    invoke: Invoke, isolated: Path
) -> None:
    text = invoke("doctor").out
    assert text.encode("cp1252").decode("cp1252") == text


def test_doctor_columns_align(invoke: Invoke, isolated: Path) -> None:
    """Alignment holds only because every generated character is one cell wide."""
    path_lines = [
        line for line in invoke("doctor").out.splitlines() if line.startswith("  project ")
    ]
    assert len(path_lines) >= 3
    location_offsets = {line.rindex("  ") + 2 for line in path_lines}
    assert len(location_offsets) == 1


def test_unconfigured_global_agents_md_still_exits_zero(
    invoke: Invoke, isolated: Path
) -> None:
    result = invoke("doctor")
    assert result.code == EXIT_OK
    assert "not configured" in result.out


def test_doctor_creates_nothing(invoke: Invoke, isolated: Path, tmp_path: Path) -> None:
    invoke("doctor")
    assert not isolated.exists()
    assert list((tmp_path / "project").iterdir()) == []


def test_doctor_never_prompts(invoke: Invoke, isolated: Path) -> None:
    """With no terminal attached, doctor still completes."""
    assert invoke("doctor").code == EXIT_OK


def test_a_non_interactive_prompt_with_no_flag_names_the_flag_and_exits_one(
    invoke: Invoke, isolated: Path
) -> None:
    """4.12: a command that would ask a question refuses, naming the flag."""
    (isolated / "snippets").mkdir(parents=True)
    (isolated / "snippets" / "base.md").write_text("---\ntitle: base\n---\n\nx\n", encoding="utf-8")
    result = invoke("init", "--snippets", "base")
    assert result.code == EXIT_ATTENTION
    assert "--mode" in result.err


def test_declining_an_optional_prompt_exits_zero(
    invoke: Invoke, isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """4.2: saying no to a confirmation is a valid outcome, not an error."""
    from mdcompose import prompts

    (isolated / "snippets").mkdir(parents=True)
    (isolated / "snippets" / "gone.md").write_text("---\ntitle: gone\n---\n\nx\n", encoding="utf-8")
    monkeypatch.setattr(prompts, "is_interactive", lambda: True)
    monkeypatch.setattr("typer.confirm", lambda *_a, **_k: False)
    result = invoke("snippet", "remove", "gone")
    assert result.code == EXIT_OK
    assert (isolated / "snippets" / "gone.md").exists()


def test_doctor_json_is_the_only_thing_on_stdout(invoke: Invoke, isolated: Path) -> None:
    result = invoke("doctor", "--json")
    assert result.code == EXIT_OK
    assert json.loads(result.out)["os"] in {"windows", "macos", "linux"}


def test_doctor_json_carries_the_same_paths_as_the_text_report(
    invoke: Invoke, isolated: Path
) -> None:
    payload = json.loads(invoke("doctor", "--json").out)
    labels = {entry["label"] for entry in payload["paths"]}
    assert {"config file", "snippet library", "global CLAUDE.md"} <= labels


def test_json_flag_works_before_the_command_too(invoke: Invoke, isolated: Path) -> None:
    before = json.loads(invoke("--json", "doctor").out)
    after = json.loads(invoke("doctor", "--json").out)
    assert before["paths"] == after["paths"]


def test_quiet_reduces_doctor_to_its_exit_code(invoke: Invoke, isolated: Path) -> None:
    result = invoke("doctor", "--quiet")
    assert result.code == EXIT_OK
    assert result.out == ""


def test_quiet_and_json_still_emit_the_requested_document(
    invoke: Invoke, isolated: Path
) -> None:
    result = invoke("doctor", "--quiet", "--json")
    assert json.loads(result.out)["os"] != ""


def test_malformed_config_needs_attention(invoke: Invoke, isolated: Path) -> None:
    isolated.mkdir(parents=True)
    config_module.config_path(isolated).write_text("{ broken", encoding="utf-8")
    result = invoke("doctor")
    assert result.code == EXIT_ATTENTION
    assert "config.json" in result.err
    assert result.out == ""


def test_an_attention_message_names_the_offending_value(
    invoke: Invoke, isolated: Path
) -> None:
    isolated.mkdir(parents=True)
    config_module.config_path(isolated).write_text(
        '{"default_mode": "sideways"}', encoding="utf-8"
    )
    result = invoke("doctor")
    assert result.code == EXIT_ATTENTION
    assert "sideways" in result.err


def test_unsupported_platform_needs_attention(
    invoke: Invoke, isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform_module.platform_module, "system", lambda: "Haiku")
    result = invoke("doctor")
    assert result.code == EXIT_ATTENTION
    assert "haiku" in result.err.lower()


def test_an_unexpected_failure_is_mdcompose_own_fault(
    invoke: Invoke, isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(**_: object) -> None:
        raise RuntimeError("something nobody predicted")

    monkeypatch.setattr(cli.report_module, "build_doctor_report", explode)
    result = invoke("doctor")
    assert result.code == EXIT_INTERNAL
    assert "bug in mdcompose" in result.err


def test_generated_non_ascii_surfaces_as_an_internal_failure(
    invoke: Invoke, isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A latent non-ASCII string is a bug, reported as one rather than crashing."""

    def emit_non_ascii(_output: object, _report: object) -> None:
        raise NonAsciiOutputError("mdcompose generated non-ASCII output (U+2014)")

    monkeypatch.setattr(cli, "render_doctor", emit_non_ascii)
    result = invoke("doctor")
    assert result.code == EXIT_INTERNAL


def test_no_command_opens_a_network_connection(
    invoke: Invoke, isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The no-network rule also forecloses fetching remote snippet content."""
    import socket

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("mdcompose attempted a network connection")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert invoke("doctor").code == EXIT_OK
    assert invoke("doctor", "--json").code == EXIT_OK
    assert invoke("--version").code == EXIT_OK


def test_no_command_records_the_invocation(
    invoke: Invoke, isolated: Path, tmp_path: Path
) -> None:
    """Nothing is written outside the files a command was asked to write."""
    invoke("doctor")
    invoke("doctor", "--json")
    invoke("--version")
    assert list((tmp_path / "project").iterdir()) == []
    assert not isolated.exists()


def report_with_warning() -> report_module.DoctorReport:
    """A report carrying a warning, so stream separation can be observed."""
    return report_module.DoctorReport(
        os_name="linux",
        is_wsl=True,
        entries=(
            report_module.PathEntry(
                label="project directory",
                resolved=ResolvedPath(
                    path=Path("/mnt/c/work"), exists=True, on_windows_mount=True
                ),
            ),
        ),
        warnings=("a path crosses the WSL and Windows filesystem boundary",),
    )


def test_a_warning_does_not_pollute_the_json_document(
    invoke: Invoke, isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stdout must stay parseable even when the same run emits a warning."""
    monkeypatch.setattr(
        cli.report_module, "build_doctor_report", lambda **_: report_with_warning()
    )
    result = invoke("doctor", "--json")
    assert json.loads(result.out)["warnings"] == [
        "a path crosses the WSL and Windows filesystem boundary"
    ]
    assert "boundary" in result.err


def test_a_warning_reaches_stderr_in_the_text_report(
    invoke: Invoke, isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli.report_module, "build_doctor_report", lambda **_: report_with_warning()
    )
    result = invoke("doctor")
    assert "boundary" in result.err
    assert "boundary" not in result.out


def test_a_warning_alone_does_not_change_the_exit_code(
    invoke: Invoke, isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli.report_module, "build_doctor_report", lambda **_: report_with_warning()
    )
    assert invoke("doctor").code == EXIT_OK


def test_a_warning_is_still_shown_in_quiet_mode(
    invoke: Invoke, isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli.report_module, "build_doctor_report", lambda **_: report_with_warning()
    )
    result = invoke("doctor", "--quiet")
    assert result.out == ""
    assert "boundary" in result.err


def test_the_error_boundary_dependency_contract_holds() -> None:
    """The boundary catches typer.TyperException, which Typer only exposes since
    it vendored Click as a private module.

    On an older Typer the attribute is absent, and because Python evaluates an
    except clause lazily, the failure would not appear until a user mistyped a
    flag, surfacing as an AttributeError instead of a usage message. This test
    fails immediately if the lower bound on Typer is ever relaxed.
    """
    assert hasattr(typer, "TyperException")
    assert hasattr(typer, "Exit")
    assert hasattr(typer, "Abort")


def test_a_non_zero_exit_from_a_command_reaches_the_shell(
    invoke: Invoke, isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Typer does not let typer.Exit propagate outside standalone mode; it turns
    it into the value app() returns.

    Ignoring that return value silently converted every non-zero outcome into
    success, and nothing noticed because the only command that raised Exit at
    the time wanted code 0 anyway. This asserts the wiring end to end.
    """

    def needs_attention(**_: object) -> report_module.DoctorReport:
        raise typer.Exit(EXIT_ATTENTION)

    monkeypatch.setattr(cli.report_module, "build_doctor_report", needs_attention)
    assert invoke("doctor").code == EXIT_ATTENTION
