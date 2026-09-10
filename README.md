# mdcompose

Manage the relationship between a project's `CLAUDE.md` and `AGENTS.md` files,
and compose their content from a personal library of reusable markdown snippets
instead of writing each project's file from scratch.

Status: the v1 command surface is complete. Composing a project, pulling
sections out of existing files (`import`), moving content between the pair
(`convert`), the `config` commands, ejecting (`eject`), and projecting the
global file to other tools' locations (`target`) all work end to end.

## Install

    pipx install mdcompose

Or, without a persistent install:

    uvx mdcompose doctor

## What exists today

    mdcompose init                compose AGENTS.md and CLAUDE.md here
    mdcompose init --global       compose the global pair instead
    mdcompose doctor              detected platform, resolved paths, drift status
    mdcompose doctor --json       the same report as one JSON document
    mdcompose snippet list        the snippets in your library
    mdcompose snippet edit <id>   open one in your editor
    mdcompose snippet remove <id> delete one
    mdcompose snippet adopt       save a project's embedded snippets to your library
    mdcompose import <file>       pull sections out of an existing CLAUDE.md or AGENTS.md
    mdcompose convert <src> <dst> move content between this project's AGENTS.md and CLAUDE.md
    mdcompose eject               stop managing a directory: remove the markers, delete the lock
    mdcompose config show         every config field and its effective value
    mdcompose config set <k> <v>  change one field
    mdcompose target add <l> <p>  register another tool's global file for projection
    mdcompose target list         registered targets and their sync status
    mdcompose --version

`doctor` has no side effects. It creates nothing, modifies nothing, and never
prompts, so it is safe to run anywhere, including in CI. It exits 1 when a
managed file has drifted from what the manifest recorded.

## Who owns what in a file

`init` owns the managed block: the comment-delimited region it regenerates from
your snippet selection on every run. `import` and `convert` own the region around
it, where your own hand-written prose lives. Neither touches the other's
territory.

That is why imported and converted content lands *outside* the block. It has no
snippet id, so putting it in the block would mean losing it on the next `init`.
Outside, it survives untouched, at the cost that mdcompose does not track it: it
is a one-off paste. To make an imported section reusable everywhere, save it with
`import --save-as-snippet <name>` and then pick it in `init`.

`import` reads a file from anywhere and never writes to it. `convert` moves
content between your two files and deletes it from the source once the target
write succeeds, so it always shows a diff and asks first.

## Targets are projections, not sources

If you run more than one AI tool, register each tool's global file once with
`target add <label> <path>`. When you write your global pair, mdcompose projects
your canonical global AGENTS.md content into a managed block inside every
registered file. The flow is one-directional: the canonical file is the only
source, a target is never read back, and mdcompose never detects or guesses a
tool's path. If you edit a target directly, `doctor` reports it out of sync
rather than propagating the change.

## Import mode and copy mode

`init` asks once how CLAUDE.md should relate to AGENTS.md, then remembers.

**Import mode** puts a live `@AGENTS.md` reference in CLAUDE.md, using Claude
Code's own mechanism. The content exists in one place, so the two files cannot
drift apart.

    CLAUDE.md                       AGENTS.md
    <!-- ...:start -->              <!-- ...:start -->
    @AGENTS.md            ------>   your composed snippets
    <!-- ...:end -->                <!-- ...:end -->

**Copy mode** materializes the content into CLAUDE.md, so the file is
self-contained and needs nothing resolved.

AGENTS.md is identical either way. It is always plain, import-agnostic markdown,
because `@import` is Claude Code specific and other tools reading AGENTS.md would
not resolve it.

Everything mdcompose writes goes inside a marked block. Anything you write around
it is yours and is never touched:

    # My own notes

    Kept exactly as written.

    <!-- mdcompose:agents-composition:start -->
    ...composed content, rewritten on every init...
    <!-- mdcompose:agents-composition:end -->

    More of my own notes, also kept.

If you hand-edit inside the block, the next `init` notices, shows you the
difference, and asks whether to keep your edit or overwrite it. Keeping it is
remembered, so it stops asking.

## The snippet library is a directory of markdown files

Your library is a flat directory, one markdown file per snippet: YAML
frontmatter followed by the body. The filename minus `.md` is the snippet id, so
there is no id field that can drift out of sync with it.

    ---
    title: Commit style
    description: How commits are written here
    tags: [git, conventions]
    applies_to: both
    stack_signals: [pyproject.toml]
    category: conventions
    order: 10
    ---

    Prefer small commits.

Every field is optional. A file with no frontmatter at all is a valid snippet.

That format is deliberate, and it is the reason there is no database. Your
library is your own writing, so it stays readable and editable in any editor,
diffs cleanly in git, and keeps working if you uninstall mdcompose or it stops
being maintained. A store that needed this tool to read it would make the tool a
dependency of your notes.

mdcompose writes nothing into that directory except snippet files. No index, no
cache, no lock file, and it never touches an entry it did not create, so keeping
the library in git or a synced folder works without the tool fighting you.

The library starts empty. mdcompose ships no snippets and offers no starter
content, because bundled opinions in your personal library would be something
you then had to curate.

## Pointing mdcompose somewhere else

`MDCOMPOSE_CONFIG_DIR` overrides where the config and the default library live.
Useful for keeping a scratch library while testing, or running more than one.

    MDCOMPOSE_CONFIG_DIR=/tmp/scratch mdcompose snippet list

## mdcompose.lock is committed

A project managed by mdcompose gets a `mdcompose.lock` in its root, and that file
belongs in version control.

It is closer to `uv.lock` than to a machine-local cache. It records which
snippets a project composed, in what order, in which mode, and it embeds each
snippet's full content. Embedding is what makes it useful to anyone else:
snippet ids resolve against a personal library nobody else has, so a manifest
carrying only ids would work for its author and nobody else. With the content
embedded, someone who clones or forks the project reproduces the same files with
an empty library.

It also records the hash of each managed block, which is how mdcompose tells its
own output apart from a hand edit. Those hashes are computed over normalized
content, so they are identical on Windows, WSL, Linux, and macOS, and a fresh
clone reports clean whichever line ending convention the checkout used.

Nothing machine-specific goes in: no absolute paths, no operating system, no
hostname. The same file is correct on every machine.

Note the naming, because it is the reverse of the npm convention some readers
will expect: here there is one file, it is committed, and it pins resolved
content. There is no second machine-local file.

## Exit codes

    0   healthy, nothing needs attention
    1   the user or the environment needs attention
    2   mdcompose itself failed

## Conventions

Output is plain ASCII. A Windows console on a cp1252 or cp437 code page cannot
encode an emoji or an em dash, so emitting one would raise an encoding error on
a platform this project treats as primary. The rule constrains what mdcompose
writes itself; content it merely carries, such as a snippet body, is never
altered.

mdcompose makes no network requests and collects no telemetry.

## How this compares to other tools

A few projects cover the same core idea of a personal snippet library composed
per project into agent config files:

- **ai-rulesmith** (npm): reusable markdown atoms, per-project selection,
  composed into a separate output file per agent, modeled on the ESLint
  shareable-config pattern.
- **ai-rulez**: profiles and remote rule includes across many target tools,
  generating a static file per tool.
- **ahmadzein/ContextVault**: a two-tier vault for Claude Code specifically,
  global at `~/.claude/vault/` and per-project at `./.claude/vault/`.

What mdcompose does that they do not:

- **Import versus copy, tied to Claude Code's real `@import`.** The others
  generate a separate static file per tool. mdcompose can keep `CLAUDE.md` as a
  live one-line reference to `AGENTS.md` so the two never drift, and falls back
  to a materialized copy only when asked.
- **Drift detection by hashing one managed block.** mdcompose owns a
  comment-delimited region and nothing else, tells its own output apart from a
  hand edit by a normalized hash, and asks before overwriting.
- **A committed lock with embedded content.** `mdcompose.lock` reproduces a
  project's files from an empty library, so a fork works without the author's
  snippets.
- **Real Windows, WSL, and mounted-drive path correctness**, treated as a
  primary target rather than an afterthought.

It deliberately does no format translation: targets receive markdown, not
Cursor rules or Copilot instructions. Converting between tool-specific formats
is a different product.

## Development

    uv sync
    uv run pytest
    uv run ruff check .
    uv run mdcompose doctor

The behavior contract that the core layer implements, written to be independent
of Python, is in `docs/core-contract.md`. See `CONTRIBUTING.md` for the
conventions CI enforces and how a change is planned.
