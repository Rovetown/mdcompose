"""The skill library: a flat directory of skills, one entry each.

Mirrors ``snippets.py`` deliberately, with one extension a snippet does not
need. A skill is usually as file-shaped as a snippet: one markdown file, YAML
frontmatter then body, filename minus the extension as the id. It may
instead be directory-shaped, `<id>/SKILL.md` plus one or more accompanying
files (a script, a config) at other relative paths inside that directory,
for a skill that needs more than a body to do its job. The two libraries are
kept separate (different directory, different config field) because a skill
is not an AGENTS.md/CLAUDE.md snippet and composes into its own file rather
than a shared block; see ``skill_composition.py`` for that half.

There is no ``applies_to`` and no ``order`` field here. ``applies_to`` exists
for snippets because one selection is split across two files (AGENTS.md and
CLAUDE.md); a skill is never split, it is its own file. ``order`` exists for
snippets because several bodies are concatenated into one block; a skill's
body is never concatenated with another skill's, so there is nothing for an
order to affect.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from mdcompose.core import files
from mdcompose.core.exit_codes import AttentionError

SKILL_SUFFIX = ".md"
SKILL_MD_FILENAME = "SKILL.md"

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
    """One skill: its id, its metadata, its body, and its accompanying files.

    The id is derived from the filename (or directory name, for a
    directory-shaped skill) and is never stored in the file, so the two cannot
    drift apart. Renaming the file or directory renames the skill.

    ``is_bundle`` and ``files`` describe the directory shape: a skill bundled
    with one or more accompanying files (a script, a config) alongside its
    ``SKILL.md``. ``files`` maps each accompanying file's path, relative to
    the skill's own directory, to its content. A file-shaped skill (the common
    case) leaves both at their defaults.
    """

    id: str
    body: str
    title: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    stack_signals: tuple[str, ...] = ()
    category: str | None = None
    path: Path | None = None
    is_bundle: bool = False
    files: Mapping[str, str] = field(default_factory=dict)

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
    """Return whether an entry in the skill library is a file-shaped skill.

    Anything that is not a regular markdown file is not a skill and is left
    entirely alone: a subdirectory, a symlink mdcompose did not create, a
    `.git` directory, a stray text file.
    """
    return path.is_file() and path.suffix == SKILL_SUFFIX


def is_skill_bundle_dir(path: Path) -> bool:
    """Return whether an entry in the skill library is a directory-shaped skill.

    A directory counts as a skill only when it contains ``SKILL.md``. A
    directory without one, such as `.git` or a stray subdirectory, is left
    entirely alone, the same as any other unrecognized entry.
    """
    return path.is_dir() and (path / SKILL_MD_FILENAME).is_file()


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
    """Read and parse one file-shaped skill."""
    return parse(files.read_text(path), id_for(path), path=path)


def read_bundle(directory: Path) -> Skill:
    """Read and parse one directory-shaped skill.

    ``SKILL.md`` is read the same way a file-shaped skill is. Every other file
    under the directory, at any depth, is an accompanying file, keyed by its
    path relative to the directory.
    """
    skill_id = directory.name
    skill_md = directory / SKILL_MD_FILENAME
    main = parse(files.read_text(skill_md), skill_id, path=skill_md)
    accompanying = {
        path.relative_to(directory).as_posix(): files.read_text(path)
        for path in _accompanying_files(directory)
    }
    return dataclasses.replace(main, is_bundle=True, files=accompanying)


def _accompanying_files(directory: Path) -> tuple[Path, ...]:
    """Every file under a bundle skill's directory except ``SKILL.md`` itself."""
    skill_md = directory / SKILL_MD_FILENAME
    return tuple(
        sorted(path for path in directory.rglob("*") if path.is_file() and path != skill_md)
    )


def load_library(library: Path) -> tuple[Skill, ...]:
    """Read every skill in the library, sorted by id.

    An absent directory is an empty library, not an error, and is not
    created. A subdirectory counts as a skill only when it holds a
    ``SKILL.md``; any other entry (a symlink, a stray file, an unrelated
    directory) is skipped in silence. A file-shaped skill and a
    directory-shaped skill sharing the same id is refused rather than one
    silently winning.
    """
    if not files.path_exists(library) or not library.is_dir():
        return ()
    entries = sorted(library.iterdir(), key=lambda item: item.name)
    file_ids = {id_for(entry) for entry in entries if is_skill_file(entry)}
    bundle_ids = {entry.name for entry in entries if is_skill_bundle_dir(entry)}
    collision = sorted(file_ids & bundle_ids)
    if collision:
        raise AttentionError(
            f"skill '{collision[0]}' exists both as a file and as a directory "
            f"in {library.as_posix()}; remove one"
        )
    return tuple(
        read(entry) if is_skill_file(entry) else read_bundle(entry)
        for entry in entries
        if is_skill_file(entry) or is_skill_bundle_dir(entry)
    )


def path_for(library: Path, skill_id: str) -> Path:
    """Return where a file-shaped skill with this id lives, without touching disk."""
    return library / f"{validate_id(skill_id)}{SKILL_SUFFIX}"


def bundle_dir_for(library: Path, skill_id: str) -> Path:
    """Return where a directory-shaped skill with this id lives, without touching disk."""
    return library / validate_id(skill_id)


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

    A file-shaped skill writes one `.md` file. A directory-shaped skill
    (``skill.is_bundle``) writes ``SKILL.md`` plus every accompanying file,
    each at its recorded relative path under the skill's own directory. The
    only thing mdcompose ever writes into the skill library is a skill's own
    files. A symlink at any write target is refused rather than followed.
    """
    if skill.is_bundle:
        return _write_bundle(library, skill)
    target = path_for(library, skill.id)
    if target.is_symlink():
        raise AttentionError(f"{target}: refusing to write a skill through a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    files.write_text(target, render(skill), line_ending=files.line_ending_for(target))
    return target


def _write_bundle(library: Path, skill: Skill) -> Path:
    directory = bundle_dir_for(library, skill.id)
    if directory.is_symlink():
        raise AttentionError(f"{directory}: refusing to write a skill through a symlink")
    directory.mkdir(parents=True, exist_ok=True)
    skill_md = directory / SKILL_MD_FILENAME
    if skill_md.is_symlink():
        raise AttentionError(f"{skill_md}: refusing to write a skill through a symlink")
    files.write_text(skill_md, render(skill), line_ending=files.line_ending_for(skill_md))
    for relative, content in skill.files.items():
        target = directory / relative
        if target.is_symlink():
            raise AttentionError(f"{target}: refusing to write a skill through a symlink")
        target.parent.mkdir(parents=True, exist_ok=True)
        files.write_text(target, content, line_ending=files.line_ending_for(target))
    return skill_md


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
