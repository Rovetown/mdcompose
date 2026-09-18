"""Operations on the skill library that a command drives: remove, adopt.

Mirrors ``library_ops.py``, not a generalization of it: a skill has no
``applies_to``, which is exactly the field `_snippet_from_manifest` reads when
reconstructing a library entry, so a shared generic layer would carry a field
that means nothing on this side. See design.md for the reasoning.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mdcompose.core import files, skills
from mdcompose.core.exit_codes import AttentionError
from mdcompose.core.manifest import Manifest, SkillEntry
from mdcompose.core.skills import Skill

Resolution = Literal["keep", "overwrite"]

KEEP: Resolution = "keep"
OVERWRITE: Resolution = "overwrite"
RESOLUTIONS: tuple[Resolution, ...] = (KEEP, OVERWRITE)

AdoptOutcome = Literal["written", "already-present", "kept", "overwritten"]


#: The filename used as the key for a skill's own body within the per-file
#: maps below, so a file-shaped and a directory-shaped skill compare through
#: one uniform representation: {"SKILL.md": body, **accompanying files}.
_SKILL_MD_KEY = skills.SKILL_MD_FILENAME


@dataclass(frozen=True, slots=True)
class Collision:
    """An embedded skill whose id already exists locally with other content.

    ``embedded`` and ``local`` each map a file's path to its content, keyed
    ``"SKILL.md"`` for the skill's own body and by relative path for every
    accompanying file, so a collision confined to one accompanying file still
    names which one, without needing a separate shape for a bundle skill.
    """

    skill_id: str
    embedded: Mapping[str, str]
    local: Mapping[str, str]

    @property
    def differing_paths(self) -> tuple[str, ...]:
        """Which files actually differ, for a message that names them."""
        paths = set(self.embedded) | set(self.local)
        return tuple(
            sorted(
                path
                for path in paths
                if not files.content_equal(self.embedded.get(path, ""), self.local.get(path, ""))
            )
        )


@dataclass(frozen=True, slots=True)
class AdoptPlan:
    """What adopting would do, worked out before anything is written."""

    to_write: tuple[Skill, ...]
    already_present: tuple[str, ...]
    collisions: tuple[Collision, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.to_write or self.already_present or self.collisions)


@dataclass(frozen=True, slots=True)
class AdoptResult:
    """What adopting actually did, per skill id."""

    outcomes: Mapping[str, AdoptOutcome]

    def ids_with(self, outcome: AdoptOutcome) -> tuple[str, ...]:
        return tuple(
            skill_id for skill_id, value in sorted(self.outcomes.items()) if value == outcome
        )


def plan_adopt(
    manifest: Manifest,
    library: skills.LibraryView,
    *,
    only: tuple[str, ...] = (),
) -> AdoptPlan:
    """Work out what adopting the manifest's embedded skills would do.

    Comparison is normalization-aware, so a skill differing from its library
    copy only by line endings or a byte order mark counts as already present
    rather than as a conflict.
    """
    if only:
        _require_known_ids(manifest, only)

    to_write: list[Skill] = []
    already_present: list[str] = []
    collisions: list[Collision] = []

    for entry in manifest.skills_in_order():
        if only and entry.id not in only:
            continue
        local = library.find(entry.id)
        embedded_files = _files_of_entry(entry)
        if local is None:
            to_write.append(_skill_from_files(entry.id, embedded_files))
            continue
        local_files = _files_of(local)
        if _files_equal(embedded_files, local_files):
            already_present.append(entry.id)
            continue
        collisions.append(Collision(skill_id=entry.id, embedded=embedded_files, local=local_files))

    return AdoptPlan(
        to_write=tuple(to_write),
        already_present=tuple(already_present),
        collisions=tuple(collisions),
    )


def _require_known_ids(manifest: Manifest, requested: tuple[str, ...]) -> None:
    known = {entry.id for entry in manifest.skills}
    unknown = sorted(set(requested) - known)
    if unknown:
        listed = ", ".join(f"'{item}'" for item in unknown)
        raise AttentionError(
            f"{manifest.source}: no embedded skill named {listed}. "
            f"Available: {', '.join(sorted(known)) or 'none'}"
        )


def _files_of_entry(entry: SkillEntry) -> dict[str, str]:
    """A manifest skill entry's files, uniform with ``_files_of``."""
    return {_SKILL_MD_KEY: entry.content, **entry.files}


def _files_of(skill: Skill) -> dict[str, str]:
    """A library skill's files, uniform whether file-shaped or a bundle."""
    return {_SKILL_MD_KEY: skill.body, **skill.files}


def _files_equal(left: Mapping[str, str], right: Mapping[str, str]) -> bool:
    """Whether two file maps hold the same paths with the same content."""
    if set(left) != set(right):
        return False
    return all(files.content_equal(left[path], right[path]) for path in left)


def _skill_from_files(skill_id: str, all_files: Mapping[str, str]) -> Skill:
    """Build a library skill from a uniform file map (see ``_files_of``).

    Only what the map carries is set: id, body, and accompanying files. A
    manifest entry records no descriptive metadata a user would write by
    hand, so the adopted skill starts minimal rather than with invented
    fields.
    """
    accompanying = {path: content for path, content in all_files.items() if path != _SKILL_MD_KEY}
    return Skill(
        id=skills.validate_id(skill_id),
        body=all_files.get(_SKILL_MD_KEY, ""),
        is_bundle=bool(accompanying),
        files=accompanying,
    )


def apply_adopt(
    plan: AdoptPlan,
    library_directory: Path,
    *,
    resolutions: Mapping[str, Resolution],
) -> AdoptResult:
    """Carry out an adoption plan, using the decision made for each collision.

    A collision with no decision is left alone rather than guessed at, so a
    caller that forgets to answer cannot silently overwrite a user's skill.
    """
    outcomes: dict[str, AdoptOutcome] = {}

    for skill in plan.to_write:
        skills.write(library_directory, skill)
        outcomes[skill.id] = "written"

    for skill_id in plan.already_present:
        outcomes[skill_id] = "already-present"

    for collision in plan.collisions:
        if resolutions.get(collision.skill_id, KEEP) == OVERWRITE:
            skills.write(
                library_directory,
                _skill_from_files(collision.skill_id, collision.embedded),
            )
            outcomes[collision.skill_id] = "overwritten"
        else:
            outcomes[collision.skill_id] = "kept"

    return AdoptResult(outcomes=outcomes)


def remove_skill(library: skills.LibraryView, skill_id: str) -> Path:
    """Delete a skill from the skill library.

    Refuses an unknown id by name. Deletes the skill's whole directory for a
    directory-shaped skill (its `SKILL.md`, every accompanying file, and the
    directory itself), or its one file otherwise. Never touches a project
    that already composed it: composition copies content, so a composed file
    keeps working after its source skill is gone.
    """
    skill = library.require(skill_id)
    if skill.path is None:
        raise AttentionError(f"skill '{skill_id}' has no file on disk to remove")
    if skill.is_bundle:
        shutil.rmtree(skill.path.parent)
        return skill.path.parent
    skill.path.unlink()
    return skill.path


def replace_body(
    library: skills.LibraryView, skill_id: str, text: str, *, relative: str | None = None
) -> Path:
    """Replace one of a skill's files, validating before writing.

    ``relative`` names which file, relative to the skill's own directory:
    left at its default (or set to ``SKILL.md`` explicitly), it targets
    `SKILL.md` and validates the candidate as a skill body, so a supplied
    body with broken frontmatter is refused and the existing skill is left
    exactly as it was. Any other relative path targets, or creates, one of a
    directory-shaped skill's accompanying files, written verbatim with no
    validation of its own; naming one against a file-shaped skill, which has
    no directory to hold it, is refused.
    """
    skill = library.require(skill_id)
    if relative is None or relative == skills.SKILL_MD_FILENAME:
        skills.parse(text, skill_id)
        default_target = skills.path_for(library.directory, skill_id)
        target = default_target if skill.path is None else skill.path
        files.write_text(target, text, line_ending=files.line_ending_for(target))
        return target

    if not skill.is_bundle or skill.path is None:
        raise AttentionError(f"skill '{skill_id}' has no accompanying files")
    target = skill.path.parent / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    files.write_text(target, text, line_ending=files.line_ending_for(target))
    return target
