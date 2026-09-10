# Changelog

All notable changes to mdcompose are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v0.1.0a0 (2026-09-10)

### Added

- mdcompose, a CLAUDE.md and AGENTS.md management CLI

### Changed

- break the cli and command import cycle (#10)
- harden the file I/O layer and fuzz the two parsers
- enforce static typing and tighten the lint rules

### Fixed

- **bump**: relock uv.lock after cz bump (#12)
