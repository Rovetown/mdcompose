# Concepts and reference

The README covers the flow.
This page covers the detail a daily user or an integrator eventually needs: the snippet format, how drift detection actually works, every path and exit code, why the tool behaves the way it does on a couple of points, and what is planned but not built yet.

The authority on exact behavior is [docs/core-contract.md](core-contract.md), written language-neutral so a port to another language reimplements a specification rather than translated Python.
This page is the readable tour; that one is the contract.

## Snippet frontmatter

A snippet is one markdown file: optional YAML frontmatter, then the body.
The filename without `.md` is the id -- there is no separate id field, so renaming a file renames the snippet, with nothing left to disagree with the new name.
A file with no frontmatter at all is still a valid snippet: the body is the whole text and every field takes its default.

| Field | Type | Meaning |
| ----- | ---- | ------- |
| `title` | string | shown to a person; the id is used when absent |
| `description` | string | one line of help |
| `tags` | list of strings | for filtering in `snippet list` |
| `applies_to` | `agents`, `claude`, or `both` | which composed file may use it |
| `stack_signals` | list of strings | filenames suggesting relevance |
| `category` | string | a grouping label |
| `order` | whole number | a requested position in the composition |
| `source_path` | string | where extraction took the content from |
| `source_heading` | string | the heading the content sat under |
| `imported_at` | string | the date the content was extracted |

`applies_to` defaults to `both`.
The last three fields are provenance, written only when `import --save-as-snippet` created the snippet by extracting a section from an existing file; they are informational and never read by composition.

An unrecognized field is ignored, so experimenting with a new one is never blocked.
A recognized field holding the wrong type is refused by name, because composing the wrong thing silently is worse than a config file being picky.

A snippet's body is composed into a target exactly as written: no variable substitution, no templating, no transformation.
No substitution syntax is reserved either, deliberately -- a snippet containing brace sequences today must not change meaning if templating is ever added later.

`order` decides position when composing: snippets carrying one sort first, ascending; snippets without one keep the order they were selected in and sort after every ordered snippet.

The library itself is a flat directory of these files -- no index, no cache, no database.
mdcompose never writes anything else into it and never touches an entry it did not create (a `.git` directory, a stray subdirectory, a file with another extension), which is what lets you keep the library under version control without the tool fighting you.

## Drift detection: normalization and hashing

A managed block's hash has to mean the same thing on Windows, under WSL, and on Linux, or a committed lock file could never be trusted across a team.
Two rules make that possible, and they only work together:

1. **Comparison is on a canonical form.** The byte order mark is removed and every line ending is converted to a single line feed before anything is compared or hashed.
   Content differing only by a BOM or by CRLF-vs-LF is the same content.
2. **Writing preserves the file's existing line-ending convention.** An existing file keeps whatever it already used; only a newly created file defaults to line feeds.

Rule 2 would make every checkout on the other convention look changed, if not for rule 1 making comparison blind to that difference.
Neither rule is safe alone; together they mean a hash computed on Windows and one computed in WSL against an identical checkout are the same hash, and a fresh clone reports clean regardless of which convention its checkout used.

The hash itself covers the managed block's content only -- never the whole file, never the marker lines -- so hand-written prose outside the block can never change the hash, and the hash cannot be forged by editing text outside mdcompose's own territory.

## Paths and `MDCOMPOSE_CONFIG_DIR`

The global config directory is one per platform: an XDG-style path on Linux and macOS, the Windows user application-data directory on native Windows. `MDCOMPOSE_CONFIG_DIR` overrides it when set to a non-empty value, on every platform.

The override exists mainly so the library and config commands can be tested, and so a script can be run, end to end without touching a real personal library.
It matters more on Windows than the name suggests: the native Windows location comes from the OS known-folder API rather than from an environment variable, so redirecting the usual application-data variable does nothing -- `MDCOMPOSE_CONFIG_DIR` is the only way to point mdcompose somewhere else there.

WSL gets no third case.
It resolves through the Linux branch (an XDG path inside the WSL filesystem), because that is already the right answer; WSL differs from plain Linux only in two things `doctor` warns about, not in where config lives:

- a path resolved under `/mnt/` (a Windows drive from inside WSL), which carries its own permission and performance characteristics, and
- an unset snippet library path under WSL, since a Windows-side install of mdcompose resolves a different library by default.

On Windows specifically, a resolved path at or under a OneDrive sync root gets its own warning -- naming the path, the sync root, and what actually breaks (a Files-On-Demand placeholder an agent reads as empty, a sync race against a `mdcompose.lock` write, the conflict copy that race leaves behind).

None of this ever blocks: `doctor` warns and still reports every other path.

## Exit codes

Every command exits with exactly one of three codes, split by whose fault the outcome is, not by how bad it is:

| Code | Meaning |
| ---- | ------- |
| 0 | Success, and nothing needs attention. |
| 1 | mdcompose worked correctly and is reporting a real condition you or the environment need to resolve -- drifted content, a missing file, an out-of-sync target. |
| 2 | mdcompose could not do its job -- a usage error, or an unexpected internal failure. |

A CI job can treat 1 and 2 alike as failure; a person reading the code learns whether to look at their own project or file a bug.
Declining an optional prompt is success, not failure -- you were asked, and you answered.

Output follows the same split: reports go to stdout, warnings/errors/prompts go to stderr, so redirecting stdout to a file never hides a warning and every command stays pipeable.
Every report command also has a `--json` mode whose stdout carries nothing but the document, for scripting.

## ASCII and no-network, stated as requirements

**Plain ASCII in everything mdcompose generates.** No em dashes, en dashes, arrows, emoji, or smart quotes in its own output, messages, or authored project documents.
This is not a style preference: a Windows console on a [cp1252](https://en.wikipedia.org/wiki/Windows-1252) or [cp437](https://en.wikipedia.org/wiki/Code_page_437) code page -- the legacy, non-Unicode character encodings a Windows terminal still defaults to -- cannot encode those characters, so emitting one raises an encoding error on a primary target platform, and emoji have ambiguous terminal width, which breaks column alignment in reports. `scripts/check_ascii.py` enforces it in CI.

The rule binds what mdcompose *generates*, never what it *transports*.
A snippet body, or a section pulled in by `import`, passes through byte-for-byte regardless of what it contains.
[README.md](../README.md) is also exempt, since GitHub and PyPI render it and it is never printed to a console -- see the Decisions log in [TODO.md](../TODO.md) for the reasoning, which mirrors the reasoning for the OneDrive warning below.

**No network requests, ever, and no telemetry.** No usage data, no analytics, no crash reports, nothing fetched from a remote source -- which also forecloses pulling snippet content from anywhere but the local library.
There is no opt-out setting, because there is nothing to opt out of.

## Registered global targets and projection

There is no single well-known location for a global `AGENTS.md`: Claude Code, Codex, and other tools each read their own path. `target add <label> <path>` registers one of those locations once; `target list` shows every registration and its sync status.

The flow is one-directional.
The file named by the global `AGENTS.md` setting is the only source of truth -- a target is never read as a source, so editing a target file directly is reported as drifted rather than being pulled back in.
Projection into a target is always a materialized copy, never an `@import` directive, because only Claude Code resolves that mechanism.
Failures are isolated per target: one unwritable or drifted target is reported by label and the run exits non-zero, but every other target still gets projected.

`eject --global` removes the managed block from every registered target as well as from the global pair, but keeps the registrations themselves, so a later global write restores projection without re-registering anything.

## Why mdcompose, specifically

A few other projects cover the same general idea -- a personal library of reusable snippets, composed per project into agent config files:

- **ai-rulesmith** (npm): reusable markdown atoms, per-project selection, composed into a separate output file per agent.
- **ai-rulez**: profiles and remote rule includes across many target tools, generating a static file per tool.
- **ContextVault**: a two-tier vault for Claude Code specifically, global and per-project.

None of them do these, which is the actual reason to reach for mdcompose instead:

- **A real `@import`, not just another generated file.** `CLAUDE.md` can hold a live `@AGENTS.md` reference using Claude Code's own import mechanism, so the content exists in exactly one place and cannot drift between the two files.
  Every alternative above generates a separate static file per tool -- there is no live reference option, because none of them target a single mechanism closely enough to use it.
- **Drift detection that only looks at what it owns.** mdcompose hashes one comment-delimited block, not the whole file, so your own hand-written notes above and below it are never a false positive and never at risk of being overwritten. `init` shows you the actual difference and asks before it touches anything.
- **A committed lock that survives an empty library.** `mdcompose.lock` embeds each snippet's full content, not just its id, so a clone or a fork reproduces the exact composed files even though the forker has none of your personal snippets.
  Nothing in it is machine-specific -- no absolute paths, no hostname, no operating system -- which is also what makes the hash comparable across every checkout.
- **Real cross-platform path correctness**, not a passing mention of it: WSL is detected and handled as Linux with two specific warnings rather than a fourth guessed-at platform, a Windows drive mounted under `/mnt/` gets its own warning, and a config or target directory sitting inside a OneDrive sync folder is flagged with the specific failure mode it causes.
- **No network requests, full stop**, including no remote snippet source.
  Composing from a repository already means trusting its authors the way you trust their build scripts; mdcompose adds no second channel on top of that.
- **Every interactive prompt has a flag.** Nothing here requires a human at a keyboard: `init --reapply`, `import --save-as-snippet`, and their siblings mean every command that can prompt can also run unattended, with the exit code contract above making the result scriptable in CI.

One more, planned rather than shipped: none of the three alternatives above appear to be aiming past agent *instructions*.
A skill file (Claude Code Skills, or whatever equivalent another tool adds) is already snippet-shaped -- frontmatter, a body, sometimes a script alongside it -- so composing those the same way is a natural extension of the same idea, not a new mechanism.
It is flagged here rather than claimed as a feature; see Planned below.

## Planned

Larger efforts, tracked in [TODO.md](../TODO.md) under Roadmap, not needed for `0.1.0` and not yet built:

- **Composing agent skills, not just AGENTS.md and CLAUDE.md.** A skill file (Claude Code Skills, or an equivalent another tool adds) is already snippet-shaped, so extending composition to skills would let a personal library of them be curated per project instead of an agent loading every skill unconditionally.
  Fewer unneeded skills loaded is context an agent never has to spend, which makes this a token-efficiency argument, not only an organizational one.
  Not scoped: a second composed-file family has to prove it reuses the existing core rather than forking it, the same bar every item below has to clear.
- **A TUI**, likely on Textual, as a second adapter over the same core: browse and filter the library, tick snippets for a project, see per-file drift, review a diff before writing.
  The CLI stays the interface that has to work unattended -- exit codes, the stdout/stderr split, `--json`, `--quiet` are CLI concepts with no TUI equivalent, so the TUI is additive, never the only way to do something.
- **A shared, browsable community snippet library, gated behind the TUI.** Concept borrowed from the skill marketplaces appearing around Claude Code Skills: a public GitHub repository as the source, crawled and indexed through GitHub's API into a locally cached, fuzzy-searchable list of community-contributed snippets, browsed and pulled into your own library one at a time from inside the TUI.
  Deliberately not a CLI feature and not on-by-default -- see "No network requests, ever" above, which this is the one planned exception to.
  The exception is scoped as narrowly as the OneDrive-detection and README-ASCII reversals were: it only ever runs from an explicit TUI action, the CLI's own network-free guarantee does not change, and pulling a community snippet in stays exactly as explicit as `snippet adopt` already requires today -- nothing is added to your library without you picking it by name.
- **Editor and IDE integrations** (a VS Code extension or a JetBrains plugin), so the library and per-project selection can be managed without leaving the editor.
  Still at the research stage: extending an existing tool may turn out to be a better use of effort than duplicating config-sync mechanics that are already solved elsewhere.
- **Ports to other languages** (Node.js/TypeScript, Go, and Rust are the likely candidates) once v1 behavior and [docs/core-contract.md](core-contract.md) are stable, for people who would rather not install Python -- not only to drop the runtime dependency, but as a native option in its own right.
- **A zero-install binary** (PyInstaller or Nuitka, or a native binary from a Go/Rust port if one lands) once file formats are stable, so a distribution channel like Homebrew, Scoop, or WinGet needs no Python at all.

None of these change [docs/core-contract.md](core-contract.md)'s behavior for the CLI; each is an additional caller of the same core, or a different runtime for the same specification.
