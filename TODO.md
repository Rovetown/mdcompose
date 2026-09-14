# Project TODO

Live work and standing decisions for **mdcompose**, the CLAUDE.md / AGENTS.md
management CLI. Everything here is either open or a decision worth keeping.

## Next

The codebase, the automation, and the account-side release setup are all done.
The repo is live at `github.com/Rovetown/mdcompose`, `v0.1.3` is on PyPI, and
the WSL demo recording did a clean-venv `pip install` against that real
published package. What is left is a short list of items that are either
genuinely still open or deliberately deferred to a future trigger (a date, a
second maintainer, a badge cache catching up). The Scorecard reasoning behind
the deferred items is in [`docs/scorecard.md`](docs/scorecard.md).

Done: CodSpeed badge added to the README badge row, `style=for-the-badge`,
placed next to the CI badge. Done: PyPI, Python-versions, and OpenSSF
Scorecard badges confirmed rendering real values, not "unknown" or a
broken-image placeholder.

### Deferred

- **OpenSSF Scorecard: Maintained check.** Scores 0 regardless of activity
  until the repository passes 90 days old; it was created 2026-09-09, so this
  clears around 2026-12-08. Nothing to do before then; revisit only to
  confirm the score actually moved once that date passes.
- **OpenSSF Scorecard: code-scanning alerts left open, not dismissed.**
  Code-Review, Branch-Protection, and Fuzzing are solo-maintainer structural
  limits (see [`docs/scorecard.md`](docs/scorecard.md), Accepted
  limitations), but "won't fix" is not a permanent label here -- the
  constraint holds only while there is one maintainer. Revisit once a second
  maintainer or a collaborator with review rights joins: Code-Review and
  Branch-Protection stop being structural at that point, and Fuzzing can be
  reconsidered on its own merits.
- **Fuzzing.** Left at 0 on purpose, not a gap to close now. Scorecard does
  not detect Python Hypothesis (already used in the parser tests), and an
  Atheris plus ClusterFuzzLite setup is out of proportion to the risk for two
  small parsers. Revisit only if the parser surface grows materially.
- **Add each new Python to the CI matrix by hand** when its final release
  ships (annual cadence, not worth automating). 3.15 is deferred until then
  (was rc2 on 2026-09-13, final due October 2026): a prerelease-specific
  version string in `uv sync --python` is not worth carrying for a few weeks
  of coverage the final release gets for free.

## Where things live

| Question | Answer lives in |
| -------- | --------------- |
| How shipped behavior is defined | [`docs/core-contract.md`](docs/core-contract.md) |
| Conventions and how to work here | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Why a decision was made | this file, Decisions log |
| What is still open | this file, the sections below |

## Decisions log

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
- **Manifest filename: `mdcompose.lock`, committed to git, and there is only one manifest.** This supersedes the earlier `.agentsmd.lock` decision and the two-file split that went with it. The original plan had a machine-local gitignored lock holding hashes plus a separate committed file holding the composition. That split existed because hashes looked machine-specific, and they are not: normalizing content before hashing makes a hash a pure function of content, identical on Windows, WSL, Linux, and macOS. Once that holds, both files carried the same information for the same audience, so merging them removed an entire capability, two commands, a precedence rule between the files, and a `.gitignore` prompt. The filename is visible rather than dotted because the file is reviewed in pull requests, and it is closer to `uv.lock` than to `package-lock.json` plus `package.json`: one file, committed, pinning resolved content. Worth noting in the README that this is the reverse of what an npm reader expects.
- **`sync` retired rather than parked.** It was originally meant to re-apply an edited snippet without reselecting, and to run the drift check. Both found better homes: drift detection is one shared operation that `doctor` reports and `init` acts on before writing, and re-applying is what re-running `init` already does when it reopens the picker with recorded selections. A separate command would have been a third caller of the same machinery with no unique job.
- **`target` built rather than left parked.** The question was whether anyone really runs two tools with separate global AGENTS.md locations. They do, and without it such a user hand-copies the same content between directories, which is the chore the tool exists to remove. The `target` command group registers a location by hand and projects the canonical global AGENTS.md into it. Projection is always copy mode, because no other tool resolves Claude Code's `@import`.
- **Python floor: `>=3.11`, and it is a policy choice rather than a technical one.** Measured rather than assumed: every runtime dependency and every dev dependency declares `>=3.10`, and the full suite passes unmodified on 3.10 through 3.14. So nothing forces a floor above 3.10. The floor sits at 3.11 because Python 3.10 reaches end of life on 2026-10-31, and a supported floor that stops receiving security fixes almost immediately buys reach that is not worth a matrix entry. 3.11 is supported until October 2027 and is what Debian 12 ships. Lowering to 3.10 is a two-line change (`requires-python` and ruff's `target-version`).
- **Typer floor matters more than the Python floor.** The CLI error boundary catches `typer.TyperException`, which is how the usage-error family is reached now that Typer 0.27 vendors Click as a private module. Versions 0.12, 0.15 and 0.19 do not expose it, and because Python evaluates an except clause lazily, an older Typer would have looked fine until a user mistyped a flag. Floor is `>=0.27` and a test asserts the attribute exists.
- **Managed block marker prefix: `mdcompose`, renamed from `agentsmd` before v1.** The markers are `<!-- mdcompose:<block-id>:start -->`. The prefix was `agentsmd`, left over from the project's former name, while every other user-visible identifier (package, CLI, config dir, `mdcompose.lock`, the `generated_by` string) already said `mdcompose`. The marker format is a frozen compatibility surface once real files carry blocks: changing it later orphans every block already written and needs a migration command. A run against a fresh checkout confirmed nothing on disk depended on the old prefix yet, so it was aligned then, which was the last free moment. Constant lives at `managed_block.MARKER_PREFIX`; `test_marker_strings_are_exactly_this` locks the exact strings.
- **Writing convention: plain ASCII everywhere.** No em dashes, en dashes, arrows, emoji, or smart quotes, in project documents or in mdcompose's own output. A Windows console on a [`cp1252`](https://en.wikipedia.org/wiki/Windows-1252) or [`cp437`](https://en.wikipedia.org/wiki/Code_page_437) code page (the legacy, non-Unicode character encodings a Windows terminal still defaults to) cannot encode them, so emitting one raises UnicodeEncodeError on the primary target platform; emoji also break column alignment through ambiguous width, and screen readers announce them verbatim. The rule constrains generated text only. Content mdcompose transports, such as a snippet body, is carried unaltered. CI enforces it with `scripts/check_ascii.py`.
  - **Exception: [`README.md`](README.md), decided during the v1 README rewrite.** The README
    is rendered by GitHub and PyPI, never printed to a console, and is meant to
    look polished: it may use `tree`-style box-drawing characters and other
    typography. `scripts/check_ascii.py` skips it. Every other document, and all
    tool output, stays under the rule. Same class of maintainer reversal as the
    OneDrive-detection decision.
- **Interface: CLI first, TUI later as a second adapter.** The CLI is the interface that must run unattended, so the scriptability contract (exit codes, stream discipline, JSON output, a flag for every prompt) belongs to it and has no TUI equivalent. See the TUI section under Roadmap.
- **Config and manifest format: JSON for both.** TOML was reconsidered specifically for the global config, since it is the one file most likely to be hand-edited and TOML allows comments, but kept as JSON for simplicity: one parser, one format, no second dependency. YAML is used only for snippet frontmatter, which is the one hand-authored file type.
- **Release model: philosophy C, commitizen `cz bump` dispatched from `bump.yml`.**
  The field has four models (see [`docs/commit-and-release-tooling.md`](docs/commit-and-release-tooling.md) section 3).
  C is chosen because commitizen is already the commit-message tool, so bump +
  changelog + tag in the same tool is one config and one mental model, and a
  `workflow_dispatch` trigger is the human gate a solo maintainer needs.
  Rejected, decision closed: A (python-semantic-release) - fully-automatic
  on-merge releases replace commitizen's role and remove the gate, out of scope;
  B (release-please) - a second bot and PR duplicating the bump-and-changelog
  role; D (towncrier) - see the changelog entry.
- **Changelog stays with commitizen; towncrier dropped.** `cz bump` writes the
  version bump, the changelog, the commit, and the tag in one step from a Jinja2
  template the project owns. Dedicated changelog generators (git-cliff,
  git-chglog) were evaluated and removed from the catalogue: a separate binary
  and config file for output polish a solo pre-1.0 project does not need.
  `towncrier` (a human-written news fragment per PR) was also dropped: its
  payoff scales with the number of outside contributors, currently zero, and
  commit subjects enforced by `cz check` are the changelog source. Revisit only
  if the commitizen template cannot produce the Keep a Changelog format, or if
  per-PR reviewed changelog lines become valuable once contributors arrive.
- **Secret scanning: gitleaks plus GitHub native, and trufflehog once.**
  gitleaks runs as a pre-commit hook (staged diff) and a CI job (full history on
  every push and PR). GitHub native secret scanning and push protection are
  enabled at repo-creation time. trufflehog runs **once, locally, over the full
  history immediately before the repo goes public** (`trufflehog git file://.
  --only-verified`), is confirmed clean, and is then never run again: not a
  hook, not a CI job. detect-secrets and per-commit trufflehog were considered
  and rejected in [`docs/commit-and-release-tooling.md`](docs/commit-and-release-tooling.md).
- **No version-derivation tooling.** `cz bump` writes `version` in
  `pyproject.toml` directly. hatch-vcs, `hatch version`, setuptools-scm,
  versioningit, and dunamai were all considered and rejected: a layer that
  derives the version from git tags at build time is more moving parts (needs
  `fetch-depth: 0` on every checkout, a `fallback-version`, and for hatch-vcs a
  `version_provider = "scm"` handshake with commitizen) than a solo project
  bumping one line per release needs. Decision closed.

- **Demo GIF recording needs a pty CPR trick, if it is ever re-recorded.**
  `questionary`'s picker sits on `prompt_toolkit`, which probes the terminal
  with a cursor-position request (`\x1b[6n`) before it will live-redraw. A
  bare `pexpect.spawn` pty never answers that probe, so the picker silently
  degrades to a static, non-redrawing render -- every keystroke lands, but
  nothing visibly updates until the final "done (N selections)" line. Fix
  used for `docs/assets/mdcompose-demo.gif`: a background thread reads the
  child pty directly (`os.read` on `child.child_fd`, not `child.expect`,
  since only one reader can drain the fd), mirrors every byte to stdout for
  `asciinema` to capture, and answers any `\x1b[6n` it sees with a plausible
  `\x1b[<row>;1R` immediately. That alone is what makes the recording a real
  live checkbox animation instead of a slideshow. The driver script and seed
  snippets were scratch-only (`temp/`), never committed, so this needs
  redoing from scratch next time.
- **PyPI's `pyversions` badge reads classifiers, not `requires-python`.**
  `pyproject.toml` had only a bare `Programming Language :: Python :: 3`
  classifier, so shields.io rendered the badge as "Python 3" instead of the
  real supported range. Fixed by listing `3.11` through `3.14` individually
  as classifiers, matching the CI matrix. Takes effect only on the next
  release; already-published metadata for a prior version is not
  retroactively fixed.
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

## CI/CD pipeline

The final plan. It is meant to be trusted and left alone: every workflow, its
trigger, its cost, and the two non-obvious wrinkles (`bump.yml` needs a PAT;
branch protection needs a bypass for it) are spelled out.

### Cost - all free

All CI runs on GitHub-hosted runners on a **public** repository: unlimited free
minutes, Linux, Windows, and macOS included. Free third-party services, each
free for public or personal-account use:

- pre-commit.ci - hosted hook runner, free for public repos
- Renovate (Mend app) - free for public repos
- Dependabot security updates - free
- OpenSSF Scorecard - free
- CodeQL - free for public repos

Excluded because metered or paid: Codecov. CodSpeed is wired (free OSS tier,
connected at codspeed.io, see the `benchmarks` job below); Coverage itself is
gated in-repo with `coverage --fail-under` and uploaded as an artifact, never
sent to a service.

One thing to confirm before wiring: `gitleaks/gitleaks-action` needs a free
`GITLEAKS_LICENSE` key **only when the repo owner is a GitHub organisation**. If
`Rovetown` is a personal account, no key is needed. Check at repo-creation time.

### Principles

- One workflow file per concern; each declares its own minimal `permissions`,
  and a failure names the concern.
- Every workflow gets a `concurrency` group keyed on the ref, cancelling
  superseded runs on the same branch.
- Every job sets `timeout-minutes`.
- Actions pinned to a full commit SHA; Renovate's
  `helpers:pinGitHubActionDigests` does the first pin and keeps them current.
- One `all-green` gate job (`needs:` every other `ci.yml` job) so branch
  protection requires one check, not twelve matrix legs.

### Workflows - final list

In the repo now: `ci.yml` (test matrix 3 OS x Python 3.11-3.14, `lint` (ruff +
`mypy` + `deptry`), `coverage`, `ascii`, `build`, plus `hooks`, `commits`,
`gitleaks`, `benchmarks` (CodSpeed, not in `all-green`'s needs), `all-green`),
`supply-chain.yml` (`licenses`, `audit`, `osv`,
`sbom`), `dependency-review.yml` (PR-only, `deny-licenses` = the copyleft
families), `release.yml` (`v*` tag), `bump.yml` (the dispatched release button),
`mutation.yml` (weekly `mutmut`), `codeql.yml`, `scorecard.yml`,
`python-eol.yml`. `.pre-commit-config.yaml` carries a `ci:` block for
pre-commit.ci. [`SECURITY.md`](SECURITY.md) points at private vulnerability reporting.

What each of the newer pieces does:

| File / job | Trigger | Does | Notes |
| --- | --- | --- | --- |
| `workflow lint` job in `ci.yml` | push, PR | `actionlint` + `zizmor` + `check-github-workflows` from pinned releases | the two hooks pre-commit.ci cannot run in its sandbox; the rest of `.pre-commit-config.yaml` is left to pre-commit.ci |
| `commits` job in `ci.yml` | PR only | `cz check --rev-range base..head` (SHAs from the PR event, via an env var) | `fetch-depth: 0` |
| `gitleaks` job in `ci.yml` | push, PR | `gitleaks-action@v2` over full history | the `hooks` job only sees the tree; this sees history |
| `all-green` job in `ci.yml` | push, PR | `if: always()`, `needs:` every other job, passes only if each is `success` or `skipped` | the single required check |
| `coverage` job in `ci.yml` | push, PR | `pytest --cov` on one platform, enforcing `fail_under` from `[tool.coverage.report]` | the matrix stays fast; only this job pays for coverage |
| `osv` job in `supply-chain.yml` | push, PR, weekly | `google/osv-scanner-action` over `uv.lock` | third source next to `pip-audit` and grype |
| `dependency-review.yml` | PR only | `actions/dependency-review-action@v4`, `fail-on-severity: moderate`, denies the copyleft licence families | inert until the repo and a PR exist |
| `mutation.yml` | weekly cron + `workflow_dispatch` | `mutmut run` over `mdcompose/core`, `mutmut results` to the job summary | `continue-on-error`, no required check; `mutmut` is the `mutation` dependency group |
| `bump.yml` | `workflow_dispatch`, input `prerelease` = choice `[stable, alpha, beta, rc]` | `cz bump --yes --changelog [--prerelease <choice>]`, commit, push `vX.Y.Z` | `fetch-depth: 0`; `if: github.ref == 'refs/heads/main'`; checks out with `secrets.RELEASE_TOKEN`; see the PAT wrinkle below |

`release.yml` prerelease gate: a `classify` job matches the tag against
`^v[0-9]+\.[0-9]+\.[0-9]+$`; a bare stable tag runs TestPyPI -> PyPI -> GitHub
Release, a prerelease tag (`v0.4.0a1`, `b1`, `rc1`) or a `workflow_dispatch` off
a branch runs TestPyPI only, with `pypi` and `github-release` gated on
`if: needs.classify.outputs.stable == 'true'`.

### The `bump.yml` PAT wrinkle (important)

A tag pushed by the built-in `GITHUB_TOKEN` **does not trigger another
workflow** (`release.yml` would never fire). And if branch protection blocks
direct pushes to `main`, the bump commit is blocked too. Both are solved the
same way:

- Create a fine-grained PAT (or a GitHub App token) with `contents: write` on
  this repo, store it as a secret (e.g. `RELEASE_TOKEN`).
- `bump.yml` checks out and pushes with that token, not `GITHUB_TOKEN`.
- In branch protection, allow that identity (the PAT's user, or the App) to
  bypass the push restriction.

The `workflow_dispatch` trigger plus the required reviewer on the `pypi`
environment remain the human gates; the PAT only lets the automated commit and
tag through.

### Dormant - shipped commented, with an `# ENABLE WHEN:` marker

- all-contributors config - ENABLE WHEN the first outside contributor lands.

The `benchmarks` job in `ci.yml` was in this list; it is now uncommented,
pinned, and connected at codspeed.io (run `34781861376`, commit `4b43aa5`,
2026-09-13, uploaded successfully after an earlier run failed with a
`401 Unauthorized` before the account-side connection existed). It runs on
every push and PR but is not in `all-green`'s needs list, so it cannot block a
merge.

(`mutation.yml` is not dormant - it ships active on a weekly cron, non-blocking.)

### Local iteration

`act` (https://github.com/nektos/act) runs the workflow files in Docker without
pushing - use it for `bump.yml` and the `ci.yml` jobs. It does not emulate
OIDC, environments, or Trusted Publishing, so `release.yml` is still validated
for real on a tag against TestPyPI.

### pre-commit: framework vs accelerator vs runner - no conflicts

- `pre-commit` is the framework and `.pre-commit-config.yaml`.
- `pre-commit-uv` builds hook envs with uv; local-dev speed only, installed
  alongside pre-commit, changes no output, pre-commit.ci ignores it.
- `pre-commit.ci` is a hosted App that runs the same config on PRs, auto-fixes,
  autoupdates weekly. A runner, not a competitor. Run the `hooks` job **or**
  pre-commit.ci, never both.

### Branch protection (repo settings, at creation time)

Require before merge to `main`: `all-green`, `supply chain / licenses`,
`supply chain / audit`, `supply chain / sbom`, `supply chain / osv`, `CodeQL`.
Require one review, require the branch up to date, require linear history
(matches the fast-forward merge style), block force-push. Enable Dependabot
alerts + security updates and private vulnerability reporting. Allow the
`bump.yml` token identity to bypass the push restriction.

### Release flow, end to end

1. Conventional Commits land on `main` (enforced by the `commits` job and the
   `cz check` hook).
2. Run `bump.yml` from the Actions tab; pick stable or a prerelease channel.
   `cz bump` writes the version and changelog, commits, pushes `vX.Y.Z` with the
   PAT.
3. `release.yml` fires on the tag: build, check, SBOM, then TestPyPI, then
   (stable tags only) PyPI behind the `pypi` reviewer, then the GitHub Release.
4. Between releases: Renovate and Dependabot keep dependencies and pinned SHAs
   current; CodeQL, Scorecard, and `python-eol.yml` run on their schedules.

### Explicitly not in the pipeline

Codecov / any other metered service (cost); git-cliff / towncrier
(commitizen writes the changelog); release-please / python-semantic-release
(rejected, philosophy C is the model); a triage bot (issue volume); hatch-vcs /
`hatch version` / setuptools-scm (no version-derivation layer; `cz bump` writes
`version` directly); trufflehog as a hook or job (it is a one-time local
pre-publish run only).

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

## Repository and release setup

Done, 2026-09-10. Plan and rationale: [`docs/publishing.md`](docs/publishing.md).
Repo public, ruleset active, `RELEASE_TOKEN` and both Actions environments
exist, both trusted publishers registered, `pre-commit.ci` enabled. Nothing
open here; live remaining work is in `Next` at the top of this file.

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

### Agent skill composition follow-ups (base feature shipped)

Composing a project's skill library into `.claude/skills/<id>/SKILL.md` the
same way AGENTS.md/CLAUDE.md are composed is done: OpenSpec change
`agent-skill-composition`, reusing the managed-block-and-manifest core rather
than forking it, per the standing bar for this Roadmap section. Two pieces
were deliberately cut from that change and are the real remaining backlog:

- [ ] A skill bundled with an accompanying script. The skill library and
  `mdcompose.lock` model shipped is single-file-per-item throughout, the same
  as the snippet library; a script-bearing skill needs a directory-shaped
  library entry, which is a real extension of the "library holds nothing but
  `.md` files" invariant and deserves its own proposal rather than folding
  into the base change.
- [ ] A `mdcompose skill` command group (list/edit/remove/adopt), mirroring
  `mdcompose snippet`. Not built: the skill library is hand-editable exactly
  like the snippet library is, so this is convenience, not a gap in what can
  be done, and can follow once the composition path has seen real use.

### Third-party integrations

- [ ] Research and, where practical, build integrations that let a user manage their content and snippet library without leaving their usual environment. Candidates are a VS Code extension or a JetBrains plugin; the TUI is tracked separately below. Before building anything new, evaluate whether extending an existing tool in this space is a better use of effort than duplicating config-sync mechanics that are already solved, so the focus stays on the snippet library and composition workflow that is not well covered elsewhere.

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
