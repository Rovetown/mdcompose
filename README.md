<div align="center">

<img src="https://raw.githubusercontent.com/Rovetown/mdcompose/main/docs/assets/mdcompose-logo.svg" alt="mdcompose" height="72">

**Compose a project's `CLAUDE.md` and `AGENTS.md` from a personal library of reusable Markdown snippets.**

</div>

[![PyPI](https://img.shields.io/pypi/v/mdcompose?style=for-the-badge)](https://pypi.org/project/mdcompose/) [![Python](https://img.shields.io/pypi/pyversions/mdcompose?style=for-the-badge)](https://pypi.org/project/mdcompose/) [![CI](https://img.shields.io/github/actions/workflow/status/Rovetown/mdcompose/ci.yml?branch=main&style=for-the-badge&label=CI)](https://github.com/Rovetown/mdcompose/actions/workflows/ci.yml) [![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/Rovetown/mdcompose?style=for-the-badge&label=scorecard)](https://scorecard.dev/viewer/?uri=github.com/Rovetown/mdcompose) [![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=for-the-badge)](https://github.com/Rovetown/mdcompose/blob/main/LICENSE) [![Downloads](https://img.shields.io/pypi/dm/mdcompose?style=for-the-badge)](https://pypi.org/project/mdcompose/)

Most repositories need the same handful of instructions for AI coding agents: how commits are written, which test command to run, which files not to touch.
mdcompose keeps those as small snippets in one place and builds each project's `AGENTS.md` and `CLAUDE.md` from the ones you pick, so you stop copying the same paragraphs between repositories.

> `mdcompose` composes Markdown.
> It is unrelated to Docker Compose; the shared `-compose` suffix is a coincidence.

## Highlights

- **One library, composed per project.** Snippets are a flat directory of Markdown files. `init` writes each project's pair from the snippets you select.
- **Import or copy.** `CLAUDE.md` can hold a live `@AGENTS.md` reference so the two files never drift, or a materialized copy when the file has to stand alone.
- **Drift detection.** mdcompose owns one comment-delimited block and hashes its contents.
  Edit inside it by hand and the next `init` shows the difference and asks before overwriting.
- **A committed lockfile.** `mdcompose.lock` embeds each snippet's content, so a clone or fork reproduces the same files with an empty library.
- **Correct paths on Windows, WSL, and Linux**, including a warning when a managed file sits inside a OneDrive-synced folder.
- **No install required.** `uvx mdcompose doctor` or `pipx run mdcompose doctor` run the real thing in a throwaway environment -- try it, or use it in a one-off script, without adding anything to your machine.
- **Skills cost tokens too, and that's next (planned).** Every skill an agent does not need loaded for a project is context spent before it has done any work.
  A skill file -- frontmatter, a body, sometimes a script -- is already snippet-shaped, so curating which skills a project loads, the same way AGENTS.md and CLAUDE.md are curated today, is the natural next composition target: real token savings, not just tidiness.
  See [docs/concepts.md](docs/concepts.md).

It makes no network requests and collects no telemetry.

## Installation

```bash
pipx install mdcompose      # recommended
uv tool install mdcompose   # if you already use uv
pip install mdcompose
```

Run it once without installing:

```bash
uvx mdcompose doctor
```

## Documentation

[docs/concepts.md](docs/concepts.md) covers the reference detail this README leaves out: the snippet frontmatter schema, how drift detection hashes and normalizes content, every path and exit code, the ASCII and no-network rationale, and what is planned but not built.
[docs/core-contract.md](docs/core-contract.md) specifies every behavior independently of the Python implementation, so a port to another language reimplements a spec rather than translating code.
[CONTRIBUTING.md](CONTRIBUTING.md) covers the conventions CI enforces and how a change is planned.

## Quickstart

The whole flow, start to finish:

<!-- demo GIF: docs/assets/mdcompose-demo.gif -- not yet recorded, see TODO.md --> <div align="center"> <img src="https://raw.githubusercontent.com/Rovetown/mdcompose/main/docs/assets/mdcompose-demo.gif" alt="mdcompose init composing a project's AGENTS.md and CLAUDE.md from selected snippets" width="720"> </div>

A snippet is one Markdown file: optional YAML frontmatter, then the body.
The filename without `.md` is the snippet id.

```bash
# 1. add a snippet to your library
mkdir -p ~/.config/mdcompose/snippets
$EDITOR ~/.config/mdcompose/snippets/commit-style.md
```

```markdown
---
title: Commit style
description: How commits are written here
applies_to: both
---

Write small commits, in Conventional Commits format.
```

```bash
# 2. compose this project's AGENTS.md and CLAUDE.md
cd my-project
mdcompose init

# 3. check the managed files against the lock at any time
mdcompose doctor
```

After `init` the project holds three managed files:

```
my-project/
├── AGENTS.md
├── CLAUDE.md
└── mdcompose.lock
```

`doctor` has no side effects.
It creates nothing, changes nothing, never prompts, and exits `1` when a managed file has drifted from the lock, so it is safe in CI.

### The command surface

```text
mdcompose init                 compose AGENTS.md and CLAUDE.md here
mdcompose init --global        compose the global pair instead
mdcompose init --reapply       recompose from the recorded selection, no picker
mdcompose doctor               platform, resolved paths, drift status
mdcompose doctor --json        the same report as one JSON document
mdcompose snippet list         the snippets in your library
mdcompose snippet edit <id>    open one in your editor
mdcompose snippet remove <id>  delete one
mdcompose snippet adopt        save a project's embedded snippets to your library
mdcompose import <file>        pull sections out of an existing CLAUDE.md or AGENTS.md
mdcompose convert <src> <dst>  move content between this project's AGENTS.md and CLAUDE.md
mdcompose eject                stop managing a directory: remove markers, delete the lock
mdcompose config show          every config field and its effective value
mdcompose config set <k> <v>   change one field
mdcompose target add <l> <p>   register another tool's global file for projection
mdcompose target list          registered targets and their sync status
```

## How it works

### Who owns what in a file

`init` owns the managed block: a comment-delimited region it regenerates from your snippet selection on every run. `import` and `convert` own the region around it, where your own hand-written prose lives.
Neither touches the other's territory.

```text
# My own notes, kept exactly as written.

<!-- mdcompose:agents-composition:start -->
...composed content, rewritten on every init...
<!-- mdcompose:agents-composition:end -->

More of my own notes, also kept.
```

Imported and converted content lands *outside* the block on purpose: it has no snippet id, so putting it inside would mean losing it on the next `init`.
To make an imported section reusable, save it with `import --save-as-snippet <name>` and pick it in `init`.

### Import mode and copy mode

`init` asks once how `CLAUDE.md` should relate to `AGENTS.md`, then remembers.

```text
Import mode                         Copy mode

CLAUDE.md        AGENTS.md           CLAUDE.md          AGENTS.md
@AGENTS.md  -->  composed snippets   composed snippets  composed snippets
```

Import mode puts a live `@AGENTS.md` reference in `CLAUDE.md` using Claude Code's own mechanism, so the content exists in one place and cannot drift.
Copy mode materializes the content into `CLAUDE.md` so the file needs nothing resolved. `AGENTS.md` is plain, import-agnostic Markdown either way, because `@import` is Claude Code specific.

### The lockfile

```
~/.config/mdcompose/snippets/        my-project/
├── commit-style.md                  ├── AGENTS.md
├── python-lbyl.md                   ├── CLAUDE.md
└── plain-ascii.md                   └── mdcompose.lock   <-- committed
```

`mdcompose.lock` records which snippets a project composed, in what order and mode, and embeds each snippet's full content.
Snippet ids resolve against a personal library nobody else has, so embedding the content is what lets a fork reproduce the project.
It also stores a normalized hash of each managed block, identical across operating systems, which is how drift detection works on a fresh clone regardless of line-ending convention.
Nothing machine-specific goes in: no absolute paths, no hostname, no operating system.

The name is the reverse of the npm convention: one file, committed, pinning resolved content.
There is no second machine-local file.

## How it compares

A few projects cover the same idea of a personal snippet library composed per project into agent config files:

- **ai-rulesmith** (npm): reusable Markdown atoms, per-project selection, composed into a separate output file per agent.
- **ai-rulez**: profiles and remote rule includes across many target tools, generating a static file per tool.
- **ContextVault**: a two-tier vault for Claude Code specifically, global and per-project.

What mdcompose does that they do not: import-versus-copy tied to Claude Code's real `@import`; drift detection by hashing one owned block; a committed lock with embedded content so a fork works without the author's library; and real Windows, WSL, and mounted-drive path correctness.
It deliberately does no format translation: a target receives Markdown, not Cursor rules or Copilot instructions.

**None of them go past agent instructions -- mdcompose plans to.** A skill file is markdown plus optional scripts, same as a snippet; composing a curated skill selection per project the way AGENTS.md and CLAUDE.md are composed today means an agent stops paying context for skills a given project never needed loaded in the first place.

See [docs/concepts.md](docs/concepts.md) for the fuller case for each point.

## Contributing

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mdcompose doctor
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow and [docs/core-contract.md](docs/core-contract.md) for the behavior specification.

## License

MIT.
See [LICENSE](LICENSE).
