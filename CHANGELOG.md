# Changelog

All notable changes to mdcompose are recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v0.3.0 (2026-09-18)

### Added

- support script-bearing skills as directory entries (#17)

## v0.2.1 (2026-09-14)

### Added

- add mdcompose skill command group

## v0.2.0 (2026-09-14)

### Added

- compose agent skills alongside AGENTS.md and CLAUDE.md

## v0.1.3 (2026-09-11)

## v0.1.2 (2026-09-11)

## v0.1.1 (2026-09-11)

## v0.1.0 (2026-09-11)

Initial public release.

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

### Security

- Release artifacts carry a SLSA build provenance attestation, signed with a
  short-lived Sigstore certificate and recorded in the GitHub attestations API.
  The provenance bundle is also attached to each GitHub Release. Verify with
  `gh attestation verify <file> --repo Rovetown/mdcompose`.
