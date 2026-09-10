# Changelog

All notable changes to mdcompose are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `init`, `doctor`, `snippet list` / `edit` / `remove` / `adopt`.
- `import <file>`: pull sections out of an existing CLAUDE.md or AGENTS.md and
  apply them to the project, with `--save-as-snippet` to promote one into the
  library.
- `convert <source> <target>`: move unmanaged content between the project's
  AGENTS.md and CLAUDE.md, with a mandatory diff.
- `eject`: remove mdcompose's markers and manifest from a directory, keeping the
  content by default or stripping it with `--strip`.
- `config show` / `set` / `unset` / `edit`.
- `target add` / `list` / `remove`: register another tool's global file and
  project the canonical global AGENTS.md into it.
- `init --reapply`: re-compose from the recorded selection without the picker.
- A warning on `doctor` and `init` when a managed path is inside a
  OneDrive-synced folder (Windows).

[Unreleased]: https://github.com/Rovetown/mdcompose/commits/main
