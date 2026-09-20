# Project TODO

Live work and standing decisions for **mdcompose**, the CLAUDE.md / AGENTS.md
management CLI. Everything here is either open or a decision worth keeping.

## Next

Everything genuinely open or deliberately deferred to a future trigger (a
date, a second maintainer). Scorecard reasoning behind the deferred items is
in [`docs/scorecard.md`](docs/scorecard.md).

### Deferred

- **OpenSSF Scorecard: Maintained check.** Scores 0 regardless of activity
  until the repository passes 90 days old; created 2026-09-09, clears around
  2026-12-08. Nothing to do before then; revisit only to confirm the score
  moved once that date passes.
- **OpenSSF Scorecard: Code-Review, Branch-Protection, and Fuzzing left open, not dismissed.**
  All three are solo-maintainer structural limits (see
  [`docs/scorecard.md`](docs/scorecard.md), Accepted limitations), not a
  permanent "won't fix": Code-Review and Branch-Protection stop being
  structural once a second maintainer or a collaborator with review rights
  joins, and Fuzzing can be reconsidered on its own merits then too. Fuzzing
  specifically: Scorecard does not detect Python Hypothesis (already used in
  the parser tests), and an Atheris plus ClusterFuzzLite setup is out of
  proportion to the risk for two small parsers; revisit only if the parser
  surface grows materially.
- **Add each new Python to the CI matrix by hand** when its final release
  ships (annual cadence, no workflow adds it for us; `python-eol.yml` only
  reminds about the floor). 3.15 is deferred until final (due October 2026).
  Tried on 2026-09-20: `uv sync --locked --python 3.15` fails because `pyyaml`
  6.0.3 has no 3.15 wheel and its sdist will not build (`Cython does not
  appear to be installed`), so the matrix entry would only fail until pyyaml
  publishes 3.15 wheels. Retry then; on success add `"3.15"` to `ci.yml`,
  `docs/publishing.md`, `docs/ci-cd.md`, `CONTRIBUTING.md`, and the
  `pyproject.toml` classifiers.

## Where things live

| Question | Answer lives in |
| -------- | --------------- |
| How shipped behavior is defined | [`docs/core-contract.md`](docs/core-contract.md) |
| Conventions and how to work here | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Why a decision was made | this file, Decisions log |
| What is still open | this file, the sections below |

## Decisions log

- **Editor integrations: live in this repo under `integrations/<editor>/`, no MCP server, no language server (2026-09-20).** One subdirectory per editor keeps one release train and one CI, at the cost of foreign toolchains (Gradle, Rust) beside the Python project; each integration keeps its own build files. An MCP server is rejected, not deferred: it would let an agent read and act on the library, and composing content is a human decision at every trust boundary in the threat model. A language server is rejected as a large dependency for little the CLI and JSON Schemas do not already give. Evidence and build order are in [`docs/editor-integrations.md`](docs/editor-integrations.md).

- **Language for v1: Python.** Chosen as the fastest language to get a working reference implementation in, not as the final or only implementation. Other languages are ports planned for later once the file formats and behavior are stable, tracked under "Additional language implementations" in the roadmap.
- **License: MIT, confirmed after the dependency audit (2026-09-09).** Every
  runtime and transitive dependency is permissive (MIT, BSD-2/3-Clause, ISC,
  Apache-2.0), so nothing constrains mdcompose's own license: it could be
  anything, permissive to strong copyleft to proprietary. MIT is kept because
  it matches the ecosystem, the dependency set is MIT-dominant, and it imposes
  nothing on a user. The tiers are recorded in `scripts/check_licenses.py`;
  `pyproject.toml` carries `license = "MIT"` and `license-files = ["LICENSE"]`.
  A funding link (Ko-fi, GitHub Sponsors) is a project-content decision, not a
  license question, and is deferred at the maintainer's request.
- **Manifest filename: `mdcompose.lock`, committed to git, and there is only one manifest.** This supersedes the earlier `.agentsmd.lock` decision and the two-file split that went with it. The original plan had a machine-local gitignored lock holding hashes plus a separate committed file holding the composition. That split existed because hashes looked machine-specific, and they are not: normalizing content before hashing makes a hash a pure function of content, identical on Windows, WSL, Linux, and macOS. Once that holds, both files carried the same information for the same audience, so merging them removed an entire capability, two commands, a precedence rule between the files, and a `.gitignore` prompt. The filename is visible rather than dotted because the file is reviewed in pull requests, and it is closer to `uv.lock` than to `package-lock.json` plus `package.json`: one file, committed, pinning resolved content.
- **`sync` retired rather than parked.** It was originally meant to re-apply an edited snippet without reselecting, and to run the drift check. Both found better homes: drift detection is one shared operation that `doctor` reports and `init` acts on before writing, and re-applying is what re-running `init` already does when it reopens the picker with recorded selections. A separate command would have been a third caller of the same machinery with no unique job.
- **`target` built rather than left parked.** The question was whether anyone really runs two tools with separate global AGENTS.md locations. They do, and without it such a user hand-copies the same content between directories, which is the chore the tool exists to remove. The `target` command group registers a location by hand and projects the canonical global AGENTS.md into it. Projection is always copy mode, because no other tool resolves Claude Code's `@import`.
- **Python floor: `>=3.11`, and it is a policy choice rather than a technical one.** Measured rather than assumed: every runtime dependency and every dev dependency declares `>=3.10`, and the full suite passes unmodified on 3.10 through 3.14. So nothing forces a floor above 3.10. The floor sits at 3.11 because Python 3.10 reaches end of life on 2026-10-31, and a supported floor that stops receiving security fixes almost immediately buys reach that is not worth a matrix entry. 3.11 is supported until October 2027 and is what Debian 12 ships. Lowering to 3.10 is a two-line change (`requires-python` and ruff's `target-version`).
- **Typer floor matters more than the Python floor.** The CLI error boundary catches `typer.TyperException`, which is how the usage-error family is reached now that Typer 0.27 vendors Click as a private module. Versions 0.12, 0.15 and 0.19 do not expose it, and because Python evaluates an except clause lazily, an older Typer would have looked fine until a user mistyped a flag. Floor is `>=0.27` and a test asserts the attribute exists.
- **Managed block marker prefix: `mdcompose`, renamed from `agentsmd` before v1.** The markers are `<!-- mdcompose:<block-id>:start -->`. The prefix was `agentsmd`, left over from the project's former name, while every other user-visible identifier (package, CLI, config dir, `mdcompose.lock`, the `generated_by` string) already said `mdcompose`. The marker format is a frozen compatibility surface once real files carry blocks: changing it later orphans every block already written and needs a migration command. A run against a fresh checkout confirmed nothing on disk depended on the old prefix yet, so it was aligned then, which was the last free moment. Constant lives at `managed_block.MARKER_PREFIX`; `test_marker_strings_are_exactly_this` locks the exact strings.
- **Writing convention: plain ASCII everywhere, `README.md` exempted.** Full rule and rationale in AGENTS.md's Conventions section; the one thing not there is that the README exemption was a maintainer reversal made during the v1 README rewrite, same class as the OneDrive-detection reversal.
- **Interface: CLI first, TUI later as a second adapter.** The CLI is the interface that must run unattended, so the scriptability contract (exit codes, stream discipline, JSON output, a flag for every prompt) belongs to it and has no TUI equivalent. See the TUI section under Roadmap.
- **Config and manifest format: JSON for both.** TOML was reconsidered specifically for the global config, since it is the one file most likely to be hand-edited and TOML allows comments, but kept as JSON for simplicity: one parser, one format, no second dependency. YAML is used only for snippet frontmatter, which is the one hand-authored file type.
- **Release model, changelog tooling, and secret scanning: picks and rejected alternatives are in [`docs/commit-and-release-tooling.md`](docs/commit-and-release-tooling.md).** Short version: commitizen `cz bump` dispatched from `bump.yml` (philosophy C) does bump + changelog + tag in one tool; gitleaks (pre-commit hook and CI job) plus GitHub native scanning run continuously, trufflehog ran once, locally, before the repo went public.
- **No version-derivation tooling.** `cz bump` writes `version` in
  `pyproject.toml` directly. hatch-vcs, `hatch version`, setuptools-scm,
  versioningit, and dunamai were all considered and rejected: a layer that
  derives the version from git tags at build time is more moving parts (needs
  `fetch-depth: 0` on every checkout, a `fallback-version`, and for hatch-vcs a
  `version_provider = "scm"` handshake with commitizen) than a solo project
  bumping one line per release needs. Decision closed.

- **Demo GIF re-recording needs a pty CPR trick.** `questionary`/`prompt_toolkit`
  probes the terminal with a cursor-position request (`\x1b[6n`) before it
  live-redraws; a bare `pexpect.spawn` pty never answers it, so the picker
  degrades to a static render. Fix: a background thread reads the child pty
  directly (`os.read`, not `child.expect`) and answers the probe with a
  plausible `\x1b[<row>;1R`. The driver script was scratch-only, never
  committed, so this needs redoing from scratch if the GIF is ever redone.
- **OpenSSF Best Practices registration is project 14614.**
  `https://www.bestpractices.dev/projects/14614`, homepage set to the GitHub
  repo URL, Passing tier across all six categories. Needed again only if the
  self-assessment has to be revisited (a criterion changes, or silver/gold
  becomes reachable with a second maintainer).

## Reference docs

- [`docs/versioning-explained.md`](docs/versioning-explained.md) - how a number becomes `0.3.2` vs `0.4.0` vs
  `1.0.0`, where `alpha` / `beta` / `rc` fit, and how a `workflow_dispatch`
  input picks the release channel.
- [`docs/commit-and-release-tooling.md`](docs/commit-and-release-tooling.md) - the tool comparison and the picks.
- [`docs/optional-tooling.md`](docs/optional-tooling.md) - everything adjacent, none required, with an
  adopt / dormant / rejected split.
- [`docs/publishing.md`](docs/publishing.md) - the publish and maintenance plan.
- [`docs/benchmarks.md`](docs/benchmarks.md) - the performance baseline and how to run the suite.
- [`docs/hardening-review.md`](docs/hardening-review.md) - the one-time file-I/O and parser review.
- [`docs/scorecard.md`](docs/scorecard.md) - the OpenSSF Scorecard score, the gap analysis, and
  what is and is not worth fixing. The action items are in the `Next` section
  above.
- [`docs/editor-integrations.md`](docs/editor-integrations.md) - the editor and IDE
  evaluation: licensing screen, capability matrix, effort and reach, build order.
- [`docs/ci-cd.md`](docs/ci-cd.md) - every workflow, its trigger and cost, the
  `bump.yml` PAT wrinkle, branch protection settings, and the release flow
  end to end.

## Standing decision: competitive landscape

Three tools cover the core idea of a personal library of reusable snippets
composed per project into agent config files, in close to the form planned here:

- `ai-rulesmith` (npm): reusable markdown atoms, per-project selection, composed
  into per-agent output files, modeled on the ESLint shareable-config pattern.
- `ai-rulez`: profiles and remote rule includes across 18 or more target tools.
- `ahmadzein/ContextVault`: a two-tier vault for Claude Code specifically, global
  at `~/.claude/vault/` and per-project at `./.claude/vault/`.

What none of them appears to cover: the explicit import-versus-copy distinction
tied to Claude Code's real `@import` mechanism, since they generate a separate
static file per tool rather than a live reference; drift detection by hashing
only a managed block; and real Windows, WSL and OneDrive path correctness.

**Decision: proceed as planned.** Raised deliberately and considered. Not
revisiting unless something materially new comes up.

## Standing decision: naming

**Project name: `mdcompose`.** Checked against PyPI, npm and GitHub with no
existing project or company found. One note for the README: the `-compose`
suffix is strongly associated with Docker Compose, so early readers may briefly
assume a Docker connection until the description corrects them. A first
impression to manage, not a conflict.

`contextsmith` was ruled out for public release, not because of another dev tool
but because it is the active brand of an existing company (ContextSmith Inc.,
B2B customer-intelligence SaaS, founded 2015, Sunnyvale). Fine for purely
personal unpublished use, never for anything released.

## Roadmap (later, deferred)

This section is TODO the same as `Next`, just longer-horizon: each item below
is real backlog, not idle brainstorming, and stays here until it is either
scoped into an OpenSpec change or explicitly dropped. The codebase-wide
quality pass is
done: strict typing enforced in CI, a ratcheting coverage floor with its own
job, a benchmark suite with a recorded baseline, the file-I/O hardening review
and parser fuzzing. `platform.py` and the interactive questionary pickers in
`init` and `import` are the accepted remaining coverage gap; their flag paths
are fully covered.

### Third-party integrations

- [ ] Build editor and IDE integrations that let a user manage their content and snippet library without leaving their usual environment. The evaluation is done and recorded in [`docs/editor-integrations.md`](docs/editor-integrations.md): twelve editors screened for cost, licensing, and extension capability, with a build order. Short version: one VS Code extension covers six editors (Open VSX plus the Microsoft Marketplace), JetBrains and Neovim follow, Zed and Helix get documented recipes only because they have no usable extension surface, and JSON Schemas for `mdcompose.lock` and snippet frontmatter reach every editor cheaply. Each integration is its own OpenSpec change, started by hand; the TUI is tracked separately below.

### TUI (terminal user interface)

Deferred branch. Not needed to make the CLI read well, which it already does;
this is a second interaction model for library-heavy workflows, built on its own
merits later. The CLI stays the primary interface. Second adapter over the same
core.

- [ ] Build a full-screen terminal interface over the existing core: browse and filter the snippet library, tick snippets for a project, see per-file drift status, review a diff before writing. Candidate library is Textual, the mature Python option, which shares no state with Typer so the two adapters stay independent.
- [ ] Keep the core untouched by it. The CLI layer is already required to be a thin adapter and the snippet picker is already specified as sitting behind a core-level selection interface, so a TUI is an additional caller rather than a refactor. Any TUI work that needs a core change is a signal the boundary leaked, and that change should be made on its own merits first.
- [ ] Do not port the `cli-surface` contract to it. Exit codes, the stdout and stderr split, `--json`, `NO_COLOR`, `--quiet`, and the rule that every prompt has a flag are CLI concepts with no TUI equivalent. They stay requirements of the CLI, which is the interface that has to work unattended in CI. A TUI is for interactive exploration only, and must never become the only way to perform an operation.
- [ ] Reuse the plain-ASCII rule where it still applies. Box drawing and layout are the framework's business, but any label or status text mdcompose authors stays ASCII, for the same Windows console reasons.
- [ ] Decide before building whether the TUI ships in the same package or as an optional extra, since Textual is heavier than the CLI needs and `pipx install mdcompose` should stay small.

### Community snippet library (TUI-gated, the one planned network exception)

Not scoped. Concept borrowed from the skill marketplaces appearing around
Claude Code Skills, adapted to a snippet library: a public GitHub repository
as the shared source, crawled and indexed through GitHub's API so it can be
browsed and fuzzy-searched locally, with individual snippets pulled into your
own library one at a time from inside the TUI.

- [ ] This is the one place the "no network requests, ever" invariant (see
  [`docs/core-contract.md`](docs/core-contract.md) section 16 and the AGENTS.md threat model) gets a
  deliberate, narrow exception, in the same spirit as the OneDrive-detection
  and README-ASCII reversals: raised on purpose, considered, decided. The CLI
  itself gains no network dependency; only this TUI-only browse action does.
- [ ] Never on by default and never reachable from the CLI. Fetching the index
  is an explicit TUI action a user takes, not something a `doctor` or `init`
  run triggers on its own.
- [ ] Security specifics for the fetch itself, not just the content it
  returns: the source is one fixed, hardcoded GitHub API host and a repository
  named explicitly (owner/name), never an arbitrary user-supplied URL, so this
  cannot become a general-purpose fetcher or an SSRF vector. Indexing resolves
  and pins a specific commit SHA rather than tracking a floating branch head,
  so what a user browses is stable and the exact source is namable in a bug
  report. Every file the crawl reads is subject to the same size limit as any
  other file mdcompose reads (section 5.1), so a maliciously huge file in the
  source repo is refused, not loaded into memory. And crawled content is
  markdown only: nothing pulled from the index is ever executed, only
  composed, the same as a locally authored snippet.
- [ ] Pulling a community snippet into your local library stays exactly as
  explicit as `snippet adopt` already requires: nothing is added without being
  picked by name, and the existing collision handling (local copy vs.
  overwrite, nothing without a decision) applies unchanged.
- [ ] Indexing needs its own trust story before this is built: a crawled
  repository is untrusted input the same way any composed snippet is (see the
  threat model in AGENTS.md), so indexing surfaces content for a human to
  read before adopting, and adopting one snippet never means trusting the
  whole source repository.
- [ ] Revisit once the TUI itself exists, since this is an additional TUI-only
  caller of the library machinery, not a reason to build the TUI sooner.

### Additional language implementations

- [ ] Once v1 behavior is stable and [`docs/core-contract.md`](docs/core-contract.md) is complete, port the CLI to one or more additional languages. Node.js/TypeScript, Go and Rust are the likely candidates. Broader than the zero-install binary below: this is about giving people who prefer not to touch Python a native option, not only about removing a runtime dependency. The contract exists so a port reimplements a specification rather than translating Python.

### Standalone binary distribution (zero install)

- [ ] Once behavior and file formats are stable, evaluate a zero-install path so end users need no Python. Candidates are PyInstaller or Nuitka, both trading binary size for no runtime dependency. If a port lands in Go or Rust, prefer shipping the binary from that instead: smaller static binaries, better cross-compilation, and a natural fit for Homebrew, Scoop, WinGet or an install script.

### Competitive landscape follow-up

- [ ] Periodically revisit how the tools listed above evolve, to confirm this project's differentiation stays genuine rather than duplicated.
