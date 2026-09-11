# Contributing to mdcompose

Thanks for taking a look.
This document covers how the project is built, the conventions that CI enforces, and how a change gets from an idea to `main`.

## Setup

    uv sync                     set up or refresh the environment
    uv run pytest               the full suite
    uv run ruff check .         lint
    uv run mypy                 static types (strict)
    uv run mdcompose doctor     sanity-check path resolution on your machine

The benchmark suite is separate and needs its own dependency group:

    uv run --group benchmark pytest tests/benchmarks

It is excluded from `uv run pytest`.
See [docs/benchmarks.md](docs/benchmarks.md) for the baseline.

Install the git hooks once per clone:

    uv run pre-commit install --install-hooks
    uv run pre-commit install --hook-type commit-msg

That runs ruff, the ASCII check, secret scanning (`gitleaks`), the workflow linters (`zizmor`, `actionlint`), and Conventional Commit validation before a commit is created. `pre-commit-uv` (a dev dependency) makes the hook environments install with uv, so the first run is fast. `uv run pre-commit run --all-files` runs everything on demand; `uv run pre-commit autoupdate` bumps the hook versions.

Python 3.11 or newer.
The suite runs on 3.11 through 3.14 in CI; run it on 3.11 before opening a pull request, because the default interpreter is newer and a few standard-library signatures differ:

    uv sync --locked --python 3.11 && uv run --no-sync pytest

## Where things live

    mdcompose/core/       behavior; knows nothing about the CLI
    mdcompose/commands/   thin Typer adapters over core
    tests/                one file per core module, plus CLI-level tests
    docs/core-contract.md the behavior spec, written language-neutral

`core/` is the product. `commands/` and `cli.py` are a thin layer that parses arguments, calls core, and formats the result.
A change that needs the CLI layer to make a decision is usually a sign the boundary leaked.

## How work is planned

[docs/core-contract.md](docs/core-contract.md) is the specification: every shipped behavior is defined there, in language-neutral terms, so a reimplementation follows a spec rather than translating this code.
A behavior change starts with an issue, is agreed there, and lands with [docs/core-contract.md](docs/core-contract.md) updated in the same commit.
Non-behavior work (docs, tooling, cleanup) needs no issue.

When implementation reveals the spec was wrong, fix the spec in the same commit and say so in the commit message.

## Conventions CI enforces

**Plain ASCII everywhere mdcompose generates text.** No em dashes, en dashes, arrows, emoji, or smart quotes, in code, comments, documents, or commit messages.
A Windows console on a [cp1252](https://en.wikipedia.org/wiki/Windows-1252) or [cp437](https://en.wikipedia.org/wiki/Code_page_437) code page (the legacy, non-Unicode character encodings a Windows terminal still defaults to) cannot encode those characters, so emitting one raises an encoding error on a primary target platform.
This constrains what mdcompose *generates*; content it *transports*, such as a snippet body, is never altered, and there are tests for both halves.

**Line length 100.
Four levels of indentation, maximum.**

**Look before you leap.** Check conditions rather than catching exceptions for control flow.
Exceptions belong at error boundaries only, and the CLI has one.

**Always `pathlib`, always an explicit encoding.** Prefer the helpers in `mdcompose/core/files.py` over raw `Path` text I/O; they normalize line endings and strip byte order marks, and they behave the same on every supported Python.

**Absolute imports, no re-exports, empty `__init__.py`.** Frozen dataclasses for values.
Comments explain why, not what.

## Invariants

A few rules in [docs/core-contract.md](docs/core-contract.md) are load-bearing and hold each other up.
Read the relevant section before changing anything near them:

- A managed block is a comment-delimited region mdcompose owns exclusively.
  Content outside it is the user's and is never modified.
  The marker format is frozen: changing it orphans every block already written.
- Hashes cover a managed block's content only, normalized so a byte order mark and the line ending convention cannot affect them.
  That is what makes a hash comparable across machines, and a committed `mdcompose.lock` possible.
- `mdcompose.lock` carries no absolute path, operating system, or hostname, and embeds snippet content so a clone reproduces the project with an empty library.
- `AGENTS.md` is always plain, import-agnostic markdown; only `CLAUDE.md` may carry an `@import`, because no other tool resolves it.
- `init` owns the managed blocks; `import`, `convert`, and `eject` own the region around them.
  Neither touches the other's territory.
- Exit codes split by fault: 0 healthy, 1 the user or environment needs attention, 2 mdcompose itself failed.
  Reports go to stdout, everything else to stderr.
  No telemetry, no network request, ever.

## Submitting a change

1. Branch from `main`.
2. Write the test first where you can; the suite is the safety net for a project whose whole job is editing other people's files.
3. Run `uv run pytest` and `uv run ruff check .`, and the 3.11 run above.
4. Keep commits focused.
   Every commit is a [Conventional Commit](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `ci:`, `refactor:`, `perf:`) with a scope where one fits; a `!` or a `BREAKING CHANGE:` footer marks an incompatible change.
   The commit-msg hook enforces this, and `uv run cz commit` walks you through a conforming message.
   The type decides the version bump at release time, so `fix:` for a bug and `feat:` for a capability, not the other way around.
5. Open a pull request describing what changed and why, and link the issue it closes.

Releases are not cut by hand: a maintainer runs the `bump.yml` workflow, which calls `cz bump` to derive the next version from the commits, update [CHANGELOG.md](CHANGELOG.md), and push the tag that publishes.
See [docs/versioning-explained.md](docs/versioning-explained.md).

## Reporting a bug

Open an issue with the smallest reproduction you can, the output of `mdcompose doctor`, and your platform and Python version.
A failing test case is the fastest possible bug report.

## Recognition

Contributors will be credited with [all-contributors](https://allcontributors.org/). It is not wired up yet because there are no outside contributors to list; the first pull request that lands will bring it in (`npx all-contributors init`).
