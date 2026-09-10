"""Doctor reporting drift: statuses, exit codes, and its read-only guarantee."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import Invocation

from mdcompose.core import files, managed_block
from mdcompose.core import manifest as manifest_module
from mdcompose.core import platform as platform_module
from mdcompose.core.exit_codes import EXIT_ATTENTION, EXIT_OK

Invoke = Callable[..., Invocation]

AGENTS_BLOCK = managed_block.AGENTS_COMPOSITION_BLOCK
COMPOSED = "Prefer small commits.\n"


def agents_file(content: str = COMPOSED) -> str:
    return (
        "User prose.\n\n"
        f"{managed_block.start_marker(AGENTS_BLOCK)}\n"
        f"{content}"
        f"{managed_block.end_marker(AGENTS_BLOCK)}\n"
    )


def manifest_text(block_hash: str) -> str:
    return json.dumps(
        {
            "schema_version": manifest_module.SCHEMA_VERSION,
            "generated_by": "mdcompose 0.1.0",
            "generated_at": "2026-09-08T10:00:00Z",
            "detected_stack": [],
            "snippets": [
                {
                    "id": "commit-style",
                    "position": 0,
                    "applies_to": "both",
                    "content": COMPOSED,
                }
            ],
            "files": {
                "agents_md": {
                    "path": "AGENTS.md",
                    "mode": "copy",
                    "managed_block_hash": block_hash,
                }
            },
        },
        indent=2,
    )


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An initialized project whose managed file matches its manifest."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "AGENTS.md").write_text(agents_file(), encoding="utf-8")
    manifest_module.manifest_path(root).write_text(
        manifest_text(files.hash_content(COMPOSED)), encoding="utf-8"
    )
    monkeypatch.setattr(platform_module, "config_dir", lambda: tmp_path / "config")
    monkeypatch.chdir(root)
    return root


def test_a_clean_project_reports_clean_and_exits_zero(invoke: Invoke, project: Path) -> None:
    result = invoke("doctor")
    assert result.code == EXIT_OK
    assert "managed files" in result.out
    assert "agents_md" in result.out
    assert "clean" in result.out


def test_a_drifted_file_needs_attention(invoke: Invoke, project: Path) -> None:
    (project / "AGENTS.md").write_text(agents_file("Hand edited.\n"), encoding="utf-8")
    result = invoke("doctor")
    assert result.code == EXIT_ATTENTION
    assert "drifted" in result.out


def test_a_missing_managed_file_needs_attention(invoke: Invoke, project: Path) -> None:
    (project / "AGENTS.md").unlink()
    result = invoke("doctor")
    assert result.code == EXIT_ATTENTION
    assert "missing" in result.out


def test_a_removed_block_needs_attention(invoke: Invoke, project: Path) -> None:
    (project / "AGENTS.md").write_text("Only prose now.\n", encoding="utf-8")
    result = invoke("doctor")
    assert result.code == EXIT_ATTENTION
    assert "block-removed" in result.out


def test_a_malformed_file_needs_attention_and_names_the_block(
    invoke: Invoke, project: Path
) -> None:
    (project / "AGENTS.md").write_text(
        f"{managed_block.start_marker(AGENTS_BLOCK)}\ncontent\n", encoding="utf-8"
    )
    result = invoke("doctor")
    assert result.code == EXIT_ATTENTION
    assert "malformed" in result.out
    assert AGENTS_BLOCK in result.out


def test_a_malformed_file_does_not_hide_the_rest_of_the_report(
    invoke: Invoke, project: Path
) -> None:
    """One unparseable file must not cost the user the whole report."""
    (project / "AGENTS.md").write_text(
        f"{managed_block.start_marker(AGENTS_BLOCK)}\ncontent\n", encoding="utf-8"
    )
    result = invoke("doctor")
    assert "platform" in result.out
    assert "project AGENTS.md" in result.out
    assert "malformed" in result.out


def test_an_uninitialized_project_is_not_a_fault(
    invoke: Invoke, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "bare"
    root.mkdir()
    monkeypatch.setattr(platform_module, "config_dir", lambda: tmp_path / "config")
    monkeypatch.chdir(root)
    result = invoke("doctor")
    assert result.code == EXIT_OK
    assert "not initialized" in result.out


def test_an_edit_outside_the_block_stays_clean(invoke: Invoke, project: Path) -> None:
    existing = (project / "AGENTS.md").read_text(encoding="utf-8")
    (project / "AGENTS.md").write_text(
        existing.replace("User prose.", "Entirely different prose."), encoding="utf-8"
    )
    assert invoke("doctor").code == EXIT_OK


def test_a_crlf_checkout_stays_clean(invoke: Invoke, project: Path) -> None:
    """A committed manifest is only viable because this holds."""
    (project / "AGENTS.md").write_bytes(
        (files.BOM + agents_file().replace("\n", "\r\n")).encode("utf-8")
    )
    assert invoke("doctor").code == EXIT_OK


def test_doctor_repairs_nothing(invoke: Invoke, project: Path) -> None:
    drifted = agents_file("Hand edited.\n")
    (project / "AGENTS.md").write_text(drifted, encoding="utf-8")
    before = {path.name: path.read_bytes() for path in project.iterdir()}
    invoke("doctor")
    after = {path.name: path.read_bytes() for path in project.iterdir()}
    assert after == before


def test_doctor_does_not_reconcile_the_manifest(invoke: Invoke, project: Path) -> None:
    manifest_before = manifest_module.manifest_path(project).read_bytes()
    (project / "AGENTS.md").write_text(agents_file("Hand edited.\n"), encoding="utf-8")
    invoke("doctor")
    assert manifest_module.manifest_path(project).read_bytes() == manifest_before


def test_doctor_does_not_prompt_on_drift(invoke: Invoke, project: Path) -> None:
    (project / "AGENTS.md").write_text(agents_file("Hand edited.\n"), encoding="utf-8")
    result = invoke("doctor")
    assert result.code == EXIT_ATTENTION
    assert result.out != ""


def test_drift_appears_in_the_json_report(invoke: Invoke, project: Path) -> None:
    payload = json.loads(invoke("doctor", "--json").out)
    assert payload["initialized"] is True
    assert payload["drift"] == [
        {
            "file": "agents_md",
            "path": (project / "AGENTS.md").as_posix(),
            "status": "clean",
            "detail": None,
        }
    ]


def test_the_json_report_says_when_a_project_is_uninitialized(
    invoke: Invoke, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "bare"
    root.mkdir()
    monkeypatch.setattr(platform_module, "config_dir", lambda: tmp_path / "config")
    monkeypatch.chdir(root)
    payload = json.loads(invoke("doctor", "--json").out)
    assert payload["initialized"] is False
    assert payload["drift"] is None


def test_the_json_exit_code_matches_the_text_one(invoke: Invoke, project: Path) -> None:
    (project / "AGENTS.md").write_text(agents_file("Hand edited.\n"), encoding="utf-8")
    assert invoke("doctor").code == invoke("doctor", "--json").code == EXIT_ATTENTION


def test_quiet_still_reports_drift_through_the_exit_code(
    invoke: Invoke, project: Path
) -> None:
    """A CI gate wants the code, not the prose."""
    (project / "AGENTS.md").write_text(agents_file("Hand edited.\n"), encoding="utf-8")
    result = invoke("doctor", "--quiet")
    assert result.code == EXIT_ATTENTION
    assert result.out == ""


def test_a_malformed_manifest_is_reported_rather_than_ignored(
    invoke: Invoke, project: Path
) -> None:
    manifest_module.manifest_path(project).write_text("{ broken", encoding="utf-8")
    result = invoke("doctor")
    assert result.code == EXIT_ATTENTION
    assert "mdcompose.lock" in result.err
