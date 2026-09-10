"""Reading mdcompose.lock, and detecting drift against what it recorded."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mdcompose.core import files, managed_block
from mdcompose.core import manifest as manifest_module
from mdcompose.core.exit_codes import AttentionError

AGENTS_BLOCK = managed_block.AGENTS_COMPOSITION_BLOCK
CLAUDE_BLOCK = managed_block.CLAUDE_MANAGED_BLOCK

COMPOSED = "Prefer small commits.\nWrite tests first.\n"
COMPOSED_HASH = files.hash_content(COMPOSED)


def agents_file(content: str = COMPOSED, *, prose: str = "User prose.\n") -> str:
    return (
        f"{prose}\n"
        f"{managed_block.start_marker(AGENTS_BLOCK)}\n"
        f"{content}"
        f"{managed_block.end_marker(AGENTS_BLOCK)}\n"
    )


def manifest_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": manifest_module.SCHEMA_VERSION,
        "generated_by": "mdcompose 0.1.0",
        "generated_at": "2026-09-08T10:00:00Z",
        "detected_stack": ["pyproject.toml"],
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
                "managed_block_hash": COMPOSED_HASH,
            }
        },
    }
    payload.update(overrides)
    return payload


def write_manifest(root: Path, payload: object) -> Path:
    target = manifest_module.manifest_path(root)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def setup_clean_project(root: Path) -> Path:
    (root / "AGENTS.md").write_text(agents_file(), encoding="utf-8")
    return write_manifest(root, manifest_payload())


def test_an_absent_manifest_means_not_initialized(tmp_path: Path) -> None:
    assert manifest_module.load_manifest(manifest_module.manifest_path(tmp_path)) is None


def test_reading_an_absent_manifest_creates_nothing(tmp_path: Path) -> None:
    manifest_module.load_manifest(manifest_module.manifest_path(tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_a_full_manifest_is_read(tmp_path: Path) -> None:
    manifest = manifest_module.load_manifest(write_manifest(tmp_path, manifest_payload()))
    assert manifest is not None
    assert manifest.schema_version == manifest_module.SCHEMA_VERSION
    assert manifest.generated_by == "mdcompose 0.1.0"
    assert manifest.detected_stack == ("pyproject.toml",)
    assert manifest.files["agents_md"].mode == "copy"
    assert manifest.files["agents_md"].managed_block_hash == COMPOSED_HASH


def test_the_manifest_is_the_committed_filename(tmp_path: Path) -> None:
    """Committed and reviewed, so it is visible rather than dotted."""
    assert manifest_module.MANIFEST_FILENAME == "mdcompose.lock"
    assert not manifest_module.MANIFEST_FILENAME.startswith(".")


def test_an_unrecognized_field_is_preserved(tmp_path: Path) -> None:
    payload = manifest_payload(future_option={"nested": True})
    manifest = manifest_module.load_manifest(write_manifest(tmp_path, payload))
    assert manifest is not None
    assert manifest.extra == {"future_option": {"nested": True}}


def test_malformed_json_names_the_path(tmp_path: Path) -> None:
    target = manifest_module.manifest_path(tmp_path)
    target.write_text("{ not json", encoding="utf-8")
    with pytest.raises(AttentionError) as raised:
        manifest_module.load_manifest(target)
    assert "mdcompose.lock" in str(raised.value)


def test_a_newer_schema_version_is_refused_not_guessed(tmp_path: Path) -> None:
    payload = manifest_payload(schema_version=manifest_module.SCHEMA_VERSION + 1)
    with pytest.raises(AttentionError) as raised:
        manifest_module.load_manifest(write_manifest(tmp_path, payload))
    message = str(raised.value)
    assert "newer mdcompose" in message
    assert "mdcompose.lock" in message


def test_a_missing_schema_version_is_refused(tmp_path: Path) -> None:
    payload = manifest_payload()
    del payload["schema_version"]
    with pytest.raises(AttentionError):
        manifest_module.load_manifest(write_manifest(tmp_path, payload))


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"detected_stack": "pyproject.toml"}, "detected_stack"),
        ({"generated_by": 7}, "generated_by"),
        ({"snippets": {}}, "snippets"),
        ({"files": []}, "files"),
    ],
)
def test_a_wrong_typed_field_names_the_field(
    tmp_path: Path, payload: dict[str, Any], expected: str
) -> None:
    with pytest.raises(AttentionError) as raised:
        manifest_module.load_manifest(write_manifest(tmp_path, manifest_payload(**payload)))
    assert expected in str(raised.value)


def test_no_machine_specific_state_is_accepted(tmp_path: Path) -> None:
    """The manifest is committed, so an absolute path would be wrong on a clone."""
    for absolute in ("/home/someone/AGENTS.md", "C:\\Users\\someone\\AGENTS.md"):
        payload = manifest_payload(
            files={
                "agents_md": {
                    "path": absolute,
                    "mode": "copy",
                    "managed_block_hash": COMPOSED_HASH,
                }
            }
        )
        with pytest.raises(AttentionError) as raised:
            manifest_module.load_manifest(write_manifest(tmp_path, payload))
        assert "absolute" in str(raised.value)


def test_a_file_entry_needs_a_valid_mode(tmp_path: Path) -> None:
    payload = manifest_payload(
        files={
            "agents_md": {
                "path": "AGENTS.md",
                "mode": "sideways",
                "managed_block_hash": COMPOSED_HASH,
            }
        }
    )
    with pytest.raises(AttentionError) as raised:
        manifest_module.load_manifest(write_manifest(tmp_path, payload))
    assert "mode" in str(raised.value)


def test_an_import_mode_entry_records_its_target(tmp_path: Path) -> None:
    payload = manifest_payload(
        files={
            "claude_md": {
                "path": "CLAUDE.md",
                "mode": "import",
                "managed_block_hash": COMPOSED_HASH,
                "imports": "AGENTS.md",
            }
        }
    )
    manifest = manifest_module.load_manifest(write_manifest(tmp_path, payload))
    assert manifest is not None
    assert manifest.files["claude_md"].imports == "AGENTS.md"


def test_a_managed_file_absent_from_the_manifest_is_unmanaged(tmp_path: Path) -> None:
    manifest = manifest_module.load_manifest(write_manifest(tmp_path, manifest_payload()))
    assert manifest is not None
    assert "claude_md" not in manifest.files


def test_embedded_content_is_available_without_any_library(tmp_path: Path) -> None:
    manifest = manifest_module.load_manifest(write_manifest(tmp_path, manifest_payload()))
    assert manifest is not None
    assert manifest.snippets[0].content == COMPOSED
    assert manifest.snippets[0].id == "commit-style"


def test_an_entry_without_content_is_refused_by_id(tmp_path: Path) -> None:
    payload = manifest_payload(snippets=[{"id": "commit-style", "position": 0}])
    with pytest.raises(AttentionError) as raised:
        manifest_module.load_manifest(write_manifest(tmp_path, payload))
    message = str(raised.value)
    assert "commit-style" in message
    assert "content" in message


def test_composition_order_comes_from_the_manifest_alone(tmp_path: Path) -> None:
    payload = manifest_payload(
        snippets=[
            {"id": "second", "position": 1, "applies_to": "both", "content": "b\n"},
            {"id": "first", "position": 0, "applies_to": "both", "content": "a\n"},
        ]
    )
    manifest = manifest_module.load_manifest(write_manifest(tmp_path, payload))
    assert manifest is not None
    assert [entry.id for entry in manifest.snippets_in_order()] == ["first", "second"]


def test_the_manifest_is_readable_in_a_diff(tmp_path: Path) -> None:
    """Formatted for a person, since it lands in pull requests."""
    raw = manifest_module.manifest_path(tmp_path)
    write_manifest(tmp_path, manifest_payload())
    text = raw.read_text(encoding="utf-8")
    assert text.count("\n") > 5
    assert "  " in text


def test_a_clean_project_reports_clean(tmp_path: Path) -> None:
    setup_clean_project(tmp_path)
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(tmp_path))
    assert manifest is not None
    drift = manifest_module.detect_drift(manifest, tmp_path)
    assert [entry.status for entry in drift] == [manifest_module.CLEAN]
    assert not any(entry.needs_attention for entry in drift)


def test_an_edit_inside_the_block_is_drift(tmp_path: Path) -> None:
    setup_clean_project(tmp_path)
    (tmp_path / "AGENTS.md").write_text(agents_file("Hand edited.\n"), encoding="utf-8")
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(tmp_path))
    assert manifest is not None
    drift = manifest_module.detect_drift(manifest, tmp_path)
    assert drift[0].status == manifest_module.DRIFTED
    assert drift[0].needs_attention


def test_an_edit_outside_the_block_is_not_drift(tmp_path: Path) -> None:
    """The whole point of hashing the block rather than the file."""
    setup_clean_project(tmp_path)
    (tmp_path / "AGENTS.md").write_text(
        agents_file(prose="Completely rewritten prose, at length.\n"), encoding="utf-8"
    )
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(tmp_path))
    assert manifest is not None
    assert manifest_module.detect_drift(manifest, tmp_path)[0].status == manifest_module.CLEAN


def test_a_missing_managed_file_is_its_own_state(tmp_path: Path) -> None:
    setup_clean_project(tmp_path)
    (tmp_path / "AGENTS.md").unlink()
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(tmp_path))
    assert manifest is not None
    assert manifest_module.detect_drift(manifest, tmp_path)[0].status == manifest_module.MISSING


def test_a_removed_block_is_its_own_state(tmp_path: Path) -> None:
    setup_clean_project(tmp_path)
    (tmp_path / "AGENTS.md").write_text("Only prose now.\n", encoding="utf-8")
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(tmp_path))
    assert manifest is not None
    entry = manifest_module.detect_drift(manifest, tmp_path)[0]
    assert entry.status == manifest_module.BLOCK_REMOVED
    assert entry.detail is not None


def test_a_malformed_file_is_its_own_state(tmp_path: Path) -> None:
    setup_clean_project(tmp_path)
    (tmp_path / "AGENTS.md").write_text(
        f"{managed_block.start_marker(AGENTS_BLOCK)}\ncontent\n", encoding="utf-8"
    )
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(tmp_path))
    assert manifest is not None
    entry = manifest_module.detect_drift(manifest, tmp_path)[0]
    assert entry.status == manifest_module.MALFORMED
    assert entry.detail is not None
    assert AGENTS_BLOCK in entry.detail


def test_every_drift_state_is_reachable_and_distinct() -> None:
    """Five states, because each names a different situation and a different fix."""
    states = {
        manifest_module.CLEAN,
        manifest_module.DRIFTED,
        manifest_module.MISSING,
        manifest_module.BLOCK_REMOVED,
        manifest_module.MALFORMED,
    }
    assert len(states) == 5


def test_drift_detection_modifies_nothing(tmp_path: Path) -> None:
    setup_clean_project(tmp_path)
    (tmp_path / "AGENTS.md").write_text(agents_file("Hand edited.\n"), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(tmp_path))
    assert manifest is not None
    manifest_module.detect_drift(manifest, tmp_path)
    after = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    assert after == before


def test_a_fresh_clone_reports_clean_whatever_the_line_endings(tmp_path: Path) -> None:
    """The property that makes a committed manifest viable at all."""
    write_manifest(tmp_path, manifest_payload())
    (tmp_path / "AGENTS.md").write_bytes(
        (files.BOM + agents_file().replace("\n", "\r\n")).encode("utf-8")
    )
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(tmp_path))
    assert manifest is not None
    assert manifest_module.detect_drift(manifest, tmp_path)[0].status == manifest_module.CLEAN


def test_each_managed_file_maps_to_its_block(tmp_path: Path) -> None:
    assert manifest_module.BLOCK_ID_BY_KEY["agents_md"] == AGENTS_BLOCK
    assert manifest_module.BLOCK_ID_BY_KEY["claude_md"] == CLAUDE_BLOCK
