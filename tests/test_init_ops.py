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
from mdcompose.core import skills as skills_module
from mdcompose.core import snippets as snippets_module
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.skills import Skill
from mdcompose.core.snippets import Snippet

LIBRARY_FILES = {
    "overview": "---\ntitle: Overview\nstack_signals: [pyproject.toml]\n---\n\nOverview.\n",
    "testing": "---\ntitle: Testing\nstack_signals: [pytest.ini]\n---\n\nTesting.\n",
    "manual": "---\ntitle: Manual\n---\n\nManual.\n",
}

SKILL_LIBRARY_FILES = {
    "code-review": (
        "---\ndescription: How we review code\nstack_signals: [pyproject.toml]\n---\n\nReview.\n"
    ),
    "release": "---\ndescription: How we release\n---\n\nRelease.\n",
}


@pytest.fixture
def library(tmp_path: Path) -> snippets_module.LibraryView:
    directory = tmp_path / "library"
    directory.mkdir()
    for name, text in LIBRARY_FILES.items():
        (directory / f"{name}.md").write_text(text, encoding="utf-8")
    return snippets_module.view(directory)


@pytest.fixture
def skill_library(tmp_path: Path) -> skills_module.LibraryView:
    directory = tmp_path / "skill-library"
    directory.mkdir()
    for name, text in SKILL_LIBRARY_FILES.items():
        (directory / f"{name}.md").write_text(text, encoding="utf-8")
    return skills_module.view(directory)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


def recording_skill_selector(
    answer: tuple[str, ...],
) -> tuple[init_ops.SkillSelector, list[tuple]]:
    calls: list[tuple] = []

    def select(available: tuple[Skill, ...], preselected: tuple[str, ...]) -> tuple[str, ...]:
        calls.append((tuple(item.id for item in available), preselected))
        return answer

    return select, calls


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


# --- skill selection, independent of the snippet selection ---


def test_an_empty_skill_library_does_not_block_planning(
    library: snippets_module.LibraryView, project: Path
) -> None:
    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=("manual",),
        requested_mode=composition.IMPORT,
        selector=None,
    )
    assert prepared.skill_selection == ()


def test_a_non_empty_skill_library_with_no_answer_refuses(
    library: snippets_module.LibraryView,
    skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    with pytest.raises(AttentionError) as raised:
        init_ops.plan(
            root=project,
            library=library,
            manifest=None,
            requested_ids=("manual",),
            requested_mode=composition.IMPORT,
            skill_library=skill_library,
        )
    assert "--skills" in str(raised.value)


def test_explicit_skill_selection_beats_the_picker(
    library: snippets_module.LibraryView,
    skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    select, calls = recording_skill_selector(("code-review",))
    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=("manual",),
        requested_mode=composition.IMPORT,
        skill_library=skill_library,
        requested_skill_ids=("release",),
        skill_selector=select,
    )
    assert calls == []
    assert [item.id for item in prepared.skill_selection] == ["release"]
    assert prepared.skill_selection_source == "flag"


def test_unknown_skill_id_is_refused(
    library: snippets_module.LibraryView,
    skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    with pytest.raises(AttentionError, match="no-such-skill"):
        init_ops.plan(
            root=project,
            library=library,
            manifest=None,
            requested_ids=("manual",),
            requested_mode=composition.IMPORT,
            skill_library=skill_library,
            requested_skill_ids=("no-such-skill",),
        )


def test_skill_stack_detection_pre_checks_the_skill_picker(
    library: snippets_module.LibraryView,
    skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    select, calls = recording_skill_selector(("code-review",))
    init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=("manual",),
        requested_mode=composition.IMPORT,
        skill_library=skill_library,
        skill_selector=select,
    )
    _, preselected = calls[0]
    assert preselected == ("code-review",)


def test_skill_selection_is_independent_of_snippet_selection(
    library: snippets_module.LibraryView,
    skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    """An empty snippet library must not stop skills from composing."""
    empty_library = snippets_module.view(project / "no-such-library")
    prepared = init_ops.plan(
        root=project,
        library=empty_library,
        manifest=None,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=skill_library,
        requested_skill_ids=("release",),
    )
    assert prepared.selection == ()
    assert [item.id for item in prepared.skill_selection] == ["release"]


# --- skill targets, writing, and delete-on-deselect ---


def test_a_selected_skill_produces_a_skill_file_target(
    library: snippets_module.LibraryView,
    skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=skill_library,
        requested_skill_ids=("code-review",),
    )
    target = prepared.target_for("code-review")
    assert target is not None
    assert target.path == project / ".claude" / "skills" / "code-review" / "SKILL.md"
    assert target.block_id == managed_block.SKILL_MANAGED_BLOCK
    assert target.frontmatter is not None
    assert "name: code-review" in target.frontmatter


def test_applying_writes_the_skill_file_and_the_manifest(
    library: snippets_module.LibraryView,
    skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=skill_library,
        requested_skill_ids=("code-review",),
    )
    result = init_ops.apply(prepared, generated_by="mdcompose test")
    skill_file = project / ".claude" / "skills" / "code-review" / "SKILL.md"
    assert skill_file.exists()
    assert "Review.\n" in skill_file.read_text(encoding="utf-8")
    assert "code-review" in result.written

    manifest = manifest_module.load_manifest(result.manifest_path)
    assert manifest is not None
    assert manifest.skills[0].id == "code-review"
    assert manifest.files["code-review"].block_id == managed_block.SKILL_MANAGED_BLOCK


def test_deselecting_a_skill_deletes_its_file_and_empty_directory(
    library: snippets_module.LibraryView,
    skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    first = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=skill_library,
        requested_skill_ids=("code-review",),
    )
    init_ops.apply(first, generated_by="mdcompose test")
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(project))
    assert manifest is not None

    second = init_ops.plan(
        root=project,
        library=library,
        manifest=manifest,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=skill_library,
        requested_skill_ids=(),
    )
    result = init_ops.apply(second, generated_by="mdcompose test")

    skill_dir = project / ".claude" / "skills" / "code-review"
    assert not skill_dir.exists()
    assert any(path.endswith("code-review/SKILL.md") for path in result.deleted) or any(
        "code-review" in path for path in result.deleted
    )


def test_deselecting_a_skill_keeps_its_directory_if_the_user_added_a_file(
    library: snippets_module.LibraryView,
    skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    first = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=skill_library,
        requested_skill_ids=("code-review",),
    )
    init_ops.apply(first, generated_by="mdcompose test")
    skill_dir = project / ".claude" / "skills" / "code-review"
    (skill_dir / "helper.py").write_text("# a script the user added\n", encoding="utf-8")

    manifest = manifest_module.load_manifest(manifest_module.manifest_path(project))
    assert manifest is not None
    second = init_ops.plan(
        root=project,
        library=library,
        manifest=manifest,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=skill_library,
        requested_skill_ids=(),
    )
    init_ops.apply(second, generated_by="mdcompose test")

    assert skill_dir.exists()
    assert (skill_dir / "helper.py").exists()
    assert not (skill_dir / "SKILL.md").exists()


def test_frontmatter_is_rewritten_when_only_the_description_changes(
    library: snippets_module.LibraryView, project: Path, tmp_path: Path
) -> None:
    directory = tmp_path / "skill-library-2"
    directory.mkdir()
    (directory / "x.md").write_text("Body.\n", encoding="utf-8")
    skill_lib = skills_module.view(directory)

    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=skill_lib,
        requested_skill_ids=("x",),
    )
    init_ops.apply(prepared, generated_by="mdcompose test")

    (directory / "x.md").write_text(
        "---\ndescription: Now described\n---\n\nBody.\n", encoding="utf-8"
    )
    skill_lib_updated = skills_module.view(directory)
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(project))
    assert manifest is not None
    second = init_ops.plan(
        root=project,
        library=library,
        manifest=manifest,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=skill_lib_updated,
        requested_skill_ids=("x",),
    )
    result = init_ops.apply(second, generated_by="mdcompose test")
    assert "x" in result.written
    text = (project / ".claude" / "skills" / "x" / "SKILL.md").read_text(encoding="utf-8")
    assert "description: Now described" in text


# --- composing skills from a manifest this machine did not write ---


def manifest_with_skill(root: Path) -> manifest_module.Manifest:
    """A manifest carrying an embedded skill this machine has never composed.

    No `.claude/skills/code-review/SKILL.md` exists on disk, matching a fresh
    clone: the manifest is the only source of the skill's content.
    """
    path = manifest_module.manifest_path(root)
    path.write_text(
        json.dumps(
            {
                "schema_version": manifest_module.SCHEMA_VERSION,
                "generated_by": "mdcompose 0.2.0",
                "generated_at": "2026-09-14T00:00:00Z",
                "detected_stack": [],
                "snippets": [],
                "skills": [{"id": "code-review", "position": 0, "content": "Review.\n"}],
                "files": {
                    "code-review": {
                        "path": ".claude/skills/code-review/SKILL.md",
                        "mode": "copy",
                        "managed_block_hash": "does-not-matter-file-is-missing",
                        "block_id": managed_block.SKILL_MANAGED_BLOCK,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    loaded = manifest_module.load_manifest(path)
    assert loaded is not None
    return loaded


def test_a_fresh_clone_composes_the_skill_from_embedded_content(
    library: snippets_module.LibraryView, project: Path
) -> None:
    manifest = manifest_with_skill(project)
    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=manifest,
        requested_mode=composition.IMPORT,
    )
    assert prepared.from_embedded is True
    assert prepared.skill_selection_source == "embedded"
    assert [item.id for item in prepared.skill_selection] == ["code-review"]
    target = prepared.target_for("code-review")
    assert target is not None
    assert target.content == "Review.\n"


def test_the_embedded_skill_shows_up_in_targets_for_the_foreign_content_confirmation(
    library: snippets_module.LibraryView, project: Path
) -> None:
    """`_confirm_foreign` in init_cmd.py shows every target generically; this
    confirms the skill target it needs to show is actually present."""
    manifest = manifest_with_skill(project)
    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=manifest,
        requested_mode=composition.IMPORT,
    )
    assert any(target.key == "code-review" for target in prepared.targets)


# --- directory-shaped (bundle) skills ---


@pytest.fixture
def bundle_skill_library(tmp_path: Path) -> skills_module.LibraryView:
    directory = tmp_path / "bundle-skill-library"
    skills_module.write(
        directory,
        Skill(
            id="lint-helper",
            body="Run the linter.\n",
            description="Lints the project",
            is_bundle=True,
            files={"scripts/lint.py": "print('lint')\n"},
        ),
    )
    return skills_module.view(directory)


def test_a_selected_bundle_skill_produces_accompanying_file_targets(
    library: snippets_module.LibraryView,
    bundle_skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=bundle_skill_library,
        requested_skill_ids=("lint-helper",),
    )
    main = prepared.target_for("lint-helper")
    assert main is not None
    assert main.frontmatter is not None

    accompanying = prepared.target_for("lint-helper:scripts/lint.py")
    assert accompanying is not None
    assert accompanying.block_id is None
    assert accompanying.frontmatter is None
    assert accompanying.content == "print('lint')\n"
    assert accompanying.path == (
        project / ".claude" / "skills" / "lint-helper" / "scripts" / "lint.py"
    )


def test_applying_writes_the_bundle_skill_and_its_accompanying_files(
    library: snippets_module.LibraryView,
    bundle_skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=bundle_skill_library,
        requested_skill_ids=("lint-helper",),
    )
    result = init_ops.apply(prepared, generated_by="mdcompose test")
    skill_dir = project / ".claude" / "skills" / "lint-helper"
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "scripts" / "lint.py").read_text(encoding="utf-8") == "print('lint')\n"
    assert "lint-helper:scripts/lint.py" in result.written

    manifest = manifest_module.load_manifest(result.manifest_path)
    assert manifest is not None
    assert manifest.skills[0].files == {"scripts/lint.py": "print('lint')\n"}
    entry = manifest.files["lint-helper:scripts/lint.py"]
    assert entry.block_id is None
    assert entry.managed_block_hash == files.hash_content("print('lint')\n")


def test_deselecting_a_bundle_skill_deletes_every_file_and_the_directory(
    library: snippets_module.LibraryView,
    bundle_skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    first = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=bundle_skill_library,
        requested_skill_ids=("lint-helper",),
    )
    init_ops.apply(first, generated_by="mdcompose test")
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(project))
    assert manifest is not None

    second = init_ops.plan(
        root=project,
        library=library,
        manifest=manifest,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=bundle_skill_library,
        requested_skill_ids=(),
    )
    result = init_ops.apply(second, generated_by="mdcompose test")

    skill_dir = project / ".claude" / "skills" / "lint-helper"
    assert not skill_dir.exists()
    assert (project / ".claude" / "skills").exists()
    assert any("lint.py" in path for path in result.deleted)


def test_removing_one_accompanying_file_deletes_only_that_file(
    library: snippets_module.LibraryView,
    bundle_skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    """The skill stays selected, but the library copy drops the script."""
    first = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=bundle_skill_library,
        requested_skill_ids=("lint-helper",),
    )
    init_ops.apply(first, generated_by="mdcompose test")
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(project))
    assert manifest is not None

    slimmed = skills_module.LibraryView(
        directory=bundle_skill_library.directory,
        skills=(
            Skill(id="lint-helper", body="Run the linter.\n", description="Lints the project"),
        ),
    )
    second = init_ops.plan(
        root=project,
        library=library,
        manifest=manifest,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=slimmed,
        requested_skill_ids=("lint-helper",),
    )
    result = init_ops.apply(second, generated_by="mdcompose test")

    skill_dir = project / ".claude" / "skills" / "lint-helper"
    assert (skill_dir / "SKILL.md").exists()
    assert not (skill_dir / "scripts").exists()
    assert any("lint.py" in path for path in result.deleted)


def test_a_hand_edited_accompanying_file_is_reported_as_drifted(
    library: snippets_module.LibraryView,
    bundle_skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    first = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=bundle_skill_library,
        requested_skill_ids=("lint-helper",),
    )
    init_ops.apply(first, generated_by="mdcompose test")
    accompanying_path = project / ".claude" / "skills" / "lint-helper" / "scripts" / "lint.py"
    accompanying_path.write_text("print('hand edited')\n", encoding="utf-8")

    manifest = manifest_module.load_manifest(manifest_module.manifest_path(project))
    assert manifest is not None
    second = init_ops.plan(
        root=project,
        library=library,
        manifest=manifest,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=bundle_skill_library,
        requested_skill_ids=("lint-helper",),
    )
    drifted_keys = {entry.key for entry in second.drifted}
    assert "lint-helper:scripts/lint.py" in drifted_keys


def test_keeping_a_drifted_accompanying_file_preserves_it_and_updates_the_hash(
    library: snippets_module.LibraryView,
    bundle_skill_library: skills_module.LibraryView,
    project: Path,
) -> None:
    first = init_ops.plan(
        root=project,
        library=library,
        manifest=None,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=bundle_skill_library,
        requested_skill_ids=("lint-helper",),
    )
    init_ops.apply(first, generated_by="mdcompose test")
    accompanying_path = project / ".claude" / "skills" / "lint-helper" / "scripts" / "lint.py"
    accompanying_path.write_text("print('hand edited')\n", encoding="utf-8")

    manifest = manifest_module.load_manifest(manifest_module.manifest_path(project))
    assert manifest is not None
    second = init_ops.plan(
        root=project,
        library=library,
        manifest=manifest,
        requested_ids=(),
        requested_mode=composition.IMPORT,
        skill_library=bundle_skill_library,
        requested_skill_ids=("lint-helper",),
    )
    init_ops.apply(
        second,
        generated_by="mdcompose test",
        drift_choices={"lint-helper:scripts/lint.py": init_ops.KEEP},
    )
    assert accompanying_path.read_text(encoding="utf-8") == "print('hand edited')\n"

    reread = manifest_module.load_manifest(manifest_module.manifest_path(project))
    assert reread is not None
    drift = manifest_module.detect_drift(reread, project)
    assert all(entry.status == manifest_module.CLEAN for entry in drift)


def manifest_with_bundle_skill(root: Path) -> manifest_module.Manifest:
    """A manifest carrying an embedded bundle skill this machine never composed."""
    path = manifest_module.manifest_path(root)
    path.write_text(
        json.dumps(
            {
                "schema_version": manifest_module.SCHEMA_VERSION,
                "generated_by": "mdcompose 0.2.0",
                "generated_at": "2026-09-14T00:00:00Z",
                "detected_stack": [],
                "snippets": [],
                "skills": [
                    {
                        "id": "lint-helper",
                        "position": 0,
                        "content": "Run the linter.\n",
                        "files": {"scripts/lint.py": "print('lint')\n"},
                    }
                ],
                "files": {
                    "lint-helper": {
                        "path": ".claude/skills/lint-helper/SKILL.md",
                        "mode": "copy",
                        "managed_block_hash": "does-not-matter-file-is-missing",
                        "block_id": managed_block.SKILL_MANAGED_BLOCK,
                    },
                    "lint-helper:scripts/lint.py": {
                        "path": ".claude/skills/lint-helper/scripts/lint.py",
                        "mode": "copy",
                        "managed_block_hash": "does-not-matter-file-is-missing",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    loaded = manifest_module.load_manifest(path)
    assert loaded is not None
    return loaded


def test_a_fresh_clone_composes_a_bundle_skill_with_its_accompanying_files(
    library: snippets_module.LibraryView, project: Path
) -> None:
    manifest = manifest_with_bundle_skill(project)
    prepared = init_ops.plan(
        root=project,
        library=library,
        manifest=manifest,
        requested_mode=composition.IMPORT,
    )
    assert prepared.from_embedded is True
    accompanying = prepared.target_for("lint-helper:scripts/lint.py")
    assert accompanying is not None
    assert accompanying.content == "print('lint')\n"
    assert any(target.key == "lint-helper:scripts/lint.py" for target in prepared.targets)
