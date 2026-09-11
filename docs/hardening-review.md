# Hardening review

A one-time pass over every file read and write in `mdcompose/`, against the five failure modes the roadmap names.
Recorded here so the reasoning survives, and so a later change that reintroduces one is easy to spot.

Every read goes through `files.read_text` and every write through `files.write_text`, with two exceptions noted below, so most of the review is about those two functions.

## 1. Unbounded read of a huge file

**Fixed.** `files.read_text` now checks `stat().st_size` against `files.MAX_READ_BYTES` (16 MiB) before reading and raises `AttentionError` naming the path when it is over.
Every file mdcompose handles is a markdown config document; a file this size is a mistake or a hostile input, and the size check runs on the resolved path so a symlink pointing at something huge is caught too.

## 2. Path traversal via a user-supplied name

**No change needed.**

- Snippet ids: `snippets.validate_id` refuses anything where `candidate != Path(candidate).name`, which rejects `/`, `\`, and `..`.
  Every library path is `library / f"{id}.md"` with a validated id.
- `convert <source> <target>`: `_resolve_pair` matches each argument against a two-entry whitelist of the project's own `AGENTS.md` and `CLAUDE.md`; anything else is refused.
- `import <file>`, `init --agents-from <file>`, and `target add <label> <path>` read or point at an arbitrary path on purpose.
  That is the documented feature: `import` reads a file from anywhere, a target is a path the user typed.
  They only ever read those paths or write an `@import` line naming them; none writes file content through a user-supplied path outside the project.

## 3. A symlink followed where it should not be

**Fixed for writes.** `files.write_text` renames a scratch file over the target (see 5), and a rename replaces a symlink with a real file rather than following it, so a write can never land outside the directory it names. `snippets.write` additionally refuses a symlinked target by name, because a symlink in the library is an entry mdcompose did not create.

Reads through a symlink are still allowed: a user who symlinks their `AGENTS.md` into place has done nothing wrong, and the size cap in 1 covers a symlink pointing at a huge file.

## 4. A TOCTOU gap between a check and a write

**Accepted.** `files.write_if_changed` and the compose and projection paths read the current file, compare, and then write, with a gap in between.
The worst case is overwriting a change made in the sub-millisecond window between the compare and the write, which is the same race any editor runs and which `doctor` would report on the next run.
mdcompose deliberately takes no concurrency lock.
The genuinely damaging outcome of a race, a half-written file, is removed by 5.

## 5. A partial write left behind on failure

**Fixed, everywhere.** `files.write_text` writes the bytes to a scratch file in the same directory and renames it over the target.
An interrupted write leaves the previous file intact, no reader sees a half-written file, and the scratch file is removed on failure.
Because every managed file, the manifest, and every snippet write goes through this one function, they all inherit the guarantee; `config.write_config` dropped the bespoke scratch dance it used to carry alone.

## Parser fuzzing

`tests/test_fuzz.py` runs `sections.parse_sections` and `managed_block.scan` over generated input, including strings shaped like markers, fences, and headings, and asserts the total-function invariant: a well-formed result, no unhandled exception, no runaway loop, every reported line span inside the document.
400 examples each, no defect found.
These are the only two functions that parse content mdcompose did not write, which is why they carry the invariant.

## The one direct-I/O exception

`platform` reads `/proc/version` directly with `Path.read_text` and `errors="replace"` to classify WSL.
The path is fixed, not user-controlled, and the content is used only for a substring test.
Everything else, including the `snippet edit` editor scratch file, goes through `files.read_text` and `files.write_text`.
