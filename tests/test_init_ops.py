"""The core-level selection and mode interfaces, driven with stubs.

The picker and the mode prompt are interactive at the CLI, so the behavior that
matters is tested here against the core interfaces they plug into. That the
interface is a plain callable is what makes this possible, and is the reason the
picker library never reaches into core.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mdcompose.core import composition, files, init_ops, managed_block
from mdcompose.core import manifest as manifest_module
from mdcompose.core import snippets as snippets_module
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.snippets import Snippet

LIBRARY_FILES = {
    "overview": "---\ntitle: Overview\nstack_signals: [pyproject.toml]\n---\n\nOverview.\n",
    "testing": "---\ntitle: Testing\nstack_signals: [pytest.ini]\n---\n\nTesting.\n",
    "manual": "---\ntitle: Manual\n---\n\nManual.\n",
}


@pytest.fixture
def library(tmp_path: Path) -> snippets_module.LibraryView:
    directory = tmp_path / "library"
    directory.mkdir()
    for name, text in LIBRARY_FILES.items():
        (directory / f"{name}.md").write_text(text, encoding="utf-8")
    return snippets_module.view(directory)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


def recording_selector(answer: tuple[str, ...]) -> tuple[init_ops.Selector, list[tuple]]:
    """A stub picker that records what it was offered and returns a fixed answer."""
    calls: list[tuple] = []

    def select(
        available: tuple[Snippet, ...], preselected: tuple[str, ...]
    ) -> tuple[str, ...]:
        calls.append((tuple(item.id for item in available), preselected))
        return answer

    return select, calls


def test_the_picker_is_offered_every_snippet(
    library: snippets_module.LibraryView, project: Path
) -> None:
    select, calls = recording_selector(("manual",))
    init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_mode=composition.IMPORT,
        selector=select,
    )
    offered, _ = calls[0]
    assert set(offered) == set(LIBRARY_FILES)


def test_the_picker_is_seeded_with_detected_snippets(
    library: snippets_module.LibraryView, project: Path
) -> None:
    (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    select, calls = recording_selector(("overview",))
    init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_mode=composition.IMPORT,
        selector=select,
    )
    _, preselected = calls[0]
    assert preselected == ("overview",)


def test_the_picker_answer_is_what_gets_composed(
    library: snippets_module.LibraryView, project: Path
) -> None:
    select, _ = recording_selector(("manual", "testing"))
    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_mode=composition.IMPORT,
        selector=select,
    )
    assert [item.id for item in prepared.selection] == ["manual", "testing"]
    assert prepared.selection_source == "picker"


def manifest_for(root: Path, ids: tuple[str, ...], mode: str) -> manifest_module.Manifest:
    """A manifest and matching files, as a previous run on this machine leaves them.

    The files have to exist and match, otherwise the state is a fresh clone
    rather than a re-run, and planning composes from embedded content instead of
    reopening the picker. That distinction is the point of both paths.
    """
    claude_content = "@AGENTS.md\n"
    composition.apply_to_file(
        root / "CLAUDE.md", managed_block.CLAUDE_MANAGED_BLOCK, claude_content
    )
    path = manifest_module.manifest_path(root)
    path.write_text(
        json.dumps(
            {
                "schema_version": manifest_module.SCHEMA_VERSION,
                "generated_by": "mdcompose 0.1.0",
                "generated_at": "2026-09-08T10:00:00Z",
                "detected_stack": [],
                "snippets": [
                    {
                        "id": name,
                        "position": index,
                        "applies_to": "both",
                        "content": f"{name}\n",
                    }
                    for index, name in enumerate(ids)
                ],
                "files": {
                    "claude_md": {
                        "path": "CLAUDE.md",
                        "mode": mode,
                        "managed_block_hash": files.hash_content(claude_content),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    loaded = manifest_module.load_manifest(path)
    assert loaded is not None
    return loaded


def test_the_picker_is_seeded_with_recorded_selections_on_a_rerun(
    library: snippets_module.LibraryView, project: Path
) -> None:
    manifest = manifest_for(project, ("manual",), composition.IMPORT)
    select, calls = recording_selector(("manual",))
    init_ops.plan(root=project, library=library, manifest=manifest, selector=select)
    _, preselected = calls[0]
    assert preselected == ("manual",)


def test_recorded_selections_beat_detection(
    library: snippets_module.LibraryView, project: Path
) -> None:
    """A snippet the user unchecked must not be re-checked on every run.

    A tool that argues with the user is worse than one that guesses wrong once.
    """
    (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    manifest = manifest_for(project, ("manual",), composition.IMPORT)
    select, calls = recording_selector(("manual",))
    init_ops.plan(root=project, library=library, manifest=manifest, selector=select)
    _, preselected = calls[0]
    assert "overview" not in preselected


def test_without_a_picker_a_rerun_uses_what_was_recorded(
    library: snippets_module.LibraryView, project: Path
) -> None:
    manifest = manifest_for(project, ("testing",), composition.COPY)
    prepared = init_ops.plan(root=project, library=library, manifest=manifest, selector=None)
    assert [item.id for item in prepared.selection] == ["testing"]
    assert prepared.selection_source == "manifest"


def test_without_a_picker_a_first_run_refuses_and_names_the_flags(
    library: snippets_module.LibraryView, project: Path
) -> None:
    with pytest.raises(AttentionError) as raised:
        init_ops.plan(
            root=project,
            library=library,
            manifest=None,
            requested_mode=composition.IMPORT,
            selector=None,
        )
    message = str(raised.value)
    assert "--snippets" in message
    assert "--yes" in message


def test_an_explicit_selection_beats_the_picker(
    library: snippets_module.LibraryView, project: Path
) -> None:
    select, calls = recording_selector(("manual",))
    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=("testing",),
        requested_mode=composition.IMPORT,
        selector=select,
    )
    assert calls == []
    assert [item.id for item in prepared.selection] == ["testing"]
    assert prepared.selection_source == "flag"


def test_accepting_detected_beats_the_picker(
    library: snippets_module.LibraryView, project: Path
) -> None:
    (project / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    select, calls = recording_selector(("manual",))
    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        accept_detected=True,
        requested_mode=composition.IMPORT,
        selector=select,
    )
    assert calls == []
    assert [item.id for item in prepared.selection] == ["testing"]
    assert prepared.selection_source == "detected"


def test_the_mode_is_asked_only_when_nothing_else_answers() -> None:
    asked: list[int] = []

    def ask() -> str:
        asked.append(1)
        return composition.COPY

    assert init_ops.resolve_mode(
        requested=composition.IMPORT, recorded=None, default=None, ask=ask
    ) == composition.IMPORT
    assert asked == []

    assert init_ops.resolve_mode(
        requested=None, recorded=composition.COPY, default=None, ask=ask
    ) == composition.COPY
    assert asked == []

    assert init_ops.resolve_mode(requested=None, recorded=None, default=None, ask=ask) == (
        composition.COPY
    )
    assert asked == [1]


def test_a_recorded_mode_beats_the_configured_default() -> None:
    assert init_ops.resolve_mode(
        requested=None, recorded=composition.IMPORT, default=composition.COPY, ask=None
    ) == composition.IMPORT


def test_with_no_answer_at_all_the_mode_question_refuses() -> None:
    with pytest.raises(AttentionError) as raised:
        init_ops.resolve_mode(requested=None, recorded=None, default=None, ask=None)
    assert "--mode" in str(raised.value)


def test_the_detected_stack_and_the_suggested_ids_are_different_things(
    library: snippets_module.LibraryView, project: Path
) -> None:
    """A signal filename is not a snippet id. Conflating them was a real bug.

    `--yes` in a directory holding a pyproject.toml failed with
    "no snippet named 'pyproject.toml'".
    """
    (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        accept_detected=True,
        requested_mode=composition.IMPORT,
    )
    assert prepared.detected_stack == ("pyproject.toml",)
    assert [item.id for item in prepared.selection] == ["overview"]


def test_planning_writes_nothing(
    library: snippets_module.LibraryView, project: Path
) -> None:
    """The plan answers every question before a single byte is written."""
    init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=("manual",),
        requested_mode=composition.IMPORT,
    )
    assert list(project.iterdir()) == []
