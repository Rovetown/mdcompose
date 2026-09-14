"""The skill library: a flat directory of markdown files, one skill each.

Mirrors ``snippets.py`` deliberately. A skill is exactly as file-shaped as a
snippet: one markdown file, YAML frontmatter then body, filename minus the
extension as the id. The two libraries are kept separate (different directory,
different config field) because a skill is not an AGENTS.md/CLAUDE.md snippet
and composes into its own file rather than a shared block; see
``skill_composition.py`` for that half.

There is no ``applies_to`` and no ``order`` field here. ``applies_to`` exists
for snippets because one selection is split across two files (AGENTS.md and
CLAUDE.md); a skill is never split, it is its own file. ``order`` exists for
snippets because several bodies are concatenated into one block; a skill's
body is never concatenated with another skill's, so there is nothing for an
order to affect.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from mdcompose.core import files
from mdcompose.core.exit_codes import AttentionError

SKILL_SUFFIX = ".md"

_FRONTMATTER_FENCE = "---"
_VALID_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: Manifest ``files`` keys reserved for the composed AGENTS.md/CLAUDE.md pair.
#: A skill id colliding with one of these would make a manifest's ``files``
#: object ambiguous between "the composed pair" and "a skill of this id", so
#: it is refused at the same point every other unusable id is refused.
RESERVED_IDS = frozenset({"agents_md", "claude_md"})

# Unrecognized frontmatter fields are simply not read, so a user experimenting
# with an extra field is never blocked, matching snippets.py.


@dataclass(frozen=True, slots=True)
class Skill:
    """One skill: its id, its metadata, and its body.

    The id is derived from the filename and is never stored in the file, so
    the two cannot drift apart. Renaming the file renames the skill.
    """

    id: str
    body: str
    title: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    stack_signals: tuple[str, ...] = ()
    category: str | None = None
    path: Path | None = None

    @property
    def display_name(self) -> str:
        """What to show a person. The title if there is one, else the id."""
        return self.id if self.title is None else self.title

    def matches_tag(self, tag: str) -> bool:
        return tag in self.tags

    def matches_category(self, category: str) -> bool:
        return self.category == category


def id_for(path: Path) -> str:
    """Return the skill id a file path implies."""
    return path.stem


def is_skill_file(path: Path) -> bool:
    """Return whether an entry in the skill library is a skill.

    Anything that is not a regular markdown file is not a skill and is left
    entirely alone: a subdirectory, a symlink mdcompose did not create, a
    `.git` directory, a stray text file.
    """
    return path.is_file() and path.suffix == SKILL_SUFFIX


def validate_id(candidate: str) -> str:
    """Return the id unchanged, or refuse a value unusable as a skill id.

    Refuses the same shapes ``snippets.validate_id`` refuses, plus the two
    manifest keys reserved for the composed AGENTS.md/CLAUDE.md pair, since a
    skill sharing one of those ids would make a manifest ambiguous.
    """
    if _VALID_ID.match(candidate) is None or candidate != Path(candidate).name:
        raise AttentionError(
            f"'{candidate}' is not usable as a skill name. Use letters, digits, "
            "dots, dashes and underscores, and no path separators."
        )
    if candidate in RESERVED_IDS:
        raise AttentionError(
            f"'{candidate}' is reserved for mdcompose's own composed files and "
            "cannot be used as a skill id."
        )
    return candidate


def parse(text: str, skill_id: str, *, path: Path | None = None) -> Skill:
    """Parse one skill from its file contents.

    A file with no frontmatter is still a valid skill: the whole text is the
    body and every field takes its default.
    """
    metadata, body = _split_frontmatter(text, skill_id)
    return Skill(
        id=skill_id,
        body=body,
        title=_as_str(metadata, "title", skill_id),
        description=_as_str(metadata, "description", skill_id),
        tags=_as_str_list(metadata, "tags", skill_id),
        stack_signals=_as_str_list(metadata, "stack_signals", skill_id),
        category=_as_str(metadata, "category", skill_id),
        path=path,
    )


def _split_frontmatter(text: str, skill_id: str) -> tuple[Mapping[str, object], str]:
    """Separate a leading YAML frontmatter block from the markdown body."""
    normalized = files.normalize(text)
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return {}, normalized

    for index in range(1, len(lines)):
        if lines[index].strip() != _FRONTMATTER_FENCE:
            continue
        block = "\n".join(lines[1:index])
        body = "\n".join(lines[index + 1 :])
        return _parse_yaml(block, skill_id), body.lstrip("\n")

    raise AttentionError(f"skill '{skill_id}': the frontmatter block is opened but never closed")


def _parse_yaml(block: str, skill_id: str) -> Mapping[str, object]:
    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        raise AttentionError(f"skill '{skill_id}': frontmatter is not valid YAML ({exc})") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise AttentionError(f"skill '{skill_id}': frontmatter must be a mapping of fields")
    return loaded


def _as_str(metadata: Mapping[str, object], key: str, skill_id: str) -> str | None:
    if key not in metadata or metadata[key] is None:
        return None
    value = metadata[key]
    if not isinstance(value, str):
        raise AttentionError(f"skill '{skill_id}': '{key}' must be a string")
    return value


def _as_str_list(metadata: Mapping[str, object], key: str, skill_id: str) -> tuple[str, ...]:
    if key not in metadata or metadata[key] is None:
        return ()
    value = metadata[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AttentionError(f"skill '{skill_id}': '{key}' must be a list of strings")
    return tuple(value)


def read(path: Path) -> Skill:
    """Read and parse one skill file."""
    return parse(files.read_text(path), id_for(path), path=path)


def load_library(library: Path) -> tuple[Skill, ...]:
    """Read every skill in the library, sorted by id.

    An absent directory is an empty library, not an error, and is not
    created. Entries that are not markdown files are skipped in silence.
    """
    if not files.path_exists(library) or not library.is_dir():
        return ()
    return tuple(
        read(path) for path in sorted(library.iterdir(), key=lambda item: item.name)
        if is_skill_file(path)
    )


def path_for(library: Path, skill_id: str) -> Path:
    """Return where a skill with this id lives, without touching the disk."""
    return library / f"{validate_id(skill_id)}{SKILL_SUFFIX}"


def find(skills: Iterable[Skill], skill_id: str) -> Skill | None:
    """Return the skill with this id, or None."""
    for skill in skills:
        if skill.id == skill_id:
            return skill
    return None


def filter_skills(
    skills: Iterable[Skill],
    *,
    tag: str | None = None,
    category: str | None = None,
) -> tuple[Skill, ...]:
    """Narrow a set of skills. Every filter supplied must match."""
    return tuple(
        skill
        for skill in skills
        if (tag is None or skill.matches_tag(tag))
        and (category is None or skill.matches_category(category))
    )


def render(skill: Skill) -> str:
    """Render a skill back to file contents: frontmatter, then body.

    Only fields that carry a value are written, so a minimal skill stays
    minimal rather than growing a wall of nulls.
    """
    metadata: dict[str, object] = {}
    if skill.title is not None:
        metadata["title"] = skill.title
    if skill.description is not None:
        metadata["description"] = skill.description
    if skill.tags:
        metadata["tags"] = list(skill.tags)
    if skill.stack_signals:
        metadata["stack_signals"] = list(skill.stack_signals)
    if skill.category is not None:
        metadata["category"] = skill.category

    if not metadata:
        return skill.body
    block = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return f"{_FRONTMATTER_FENCE}\n{block}{_FRONTMATTER_FENCE}\n\n{skill.body}"


def write(library: Path, skill: Skill) -> Path:
    """Write a skill into the library, creating the directory if needed.

    The only thing mdcompose ever writes into the skill library is a skill
    file. A symlink at the target is refused rather than followed.
    """
    target = path_for(library, skill.id)
    if target.is_symlink():
        raise AttentionError(f"{target}: refusing to write a skill through a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    files.write_text(target, render(skill), line_ending=files.line_ending_for(target))
    return target


@dataclass(frozen=True, slots=True)
class LibraryView:
    """The skill library as one value, so a command reads the disk once."""

    directory: Path
    skills: tuple[Skill, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not self.skills

    @property
    def exists(self) -> bool:
        return files.path_exists(self.directory)

    def find(self, skill_id: str) -> Skill | None:
        return find(self.skills, skill_id)

    def require(self, skill_id: str) -> Skill:
        """Return the named skill, or refuse with the id named."""
        skill = self.find(skill_id)
        if skill is None:
            raise AttentionError(
                f"no skill '{skill_id}' in the skill library at {self.directory.as_posix()}"
            )
        return skill


def view(library: Path) -> LibraryView:
    """Read the skill library once and return it as a value."""
    return LibraryView(directory=library, skills=load_library(library))
