# Project TODO

Live work and standing decisions for **mdcompose**, the CLAUDE.md / AGENTS.md
management CLI. Everything here is either open or a decision worth keeping.

## Next

The codebase and the automation are done. The repo is live at
`github.com/Rovetown/mdcompose` and the account-side setup in "Repository and
release setup" below is complete (ruleset, `RELEASE_TOKEN`, the `pypi` and
`testpypi` environments, both trusted publishers, Dependabot, private
vulnerability reporting). What remains is the first release, a few follow-ups,
and a set of OpenSSF Scorecard items folded into the sequence at the step each
one belongs to. The Scorecard reasoning is in [`docs/scorecard.md`](docs/scorecard.md).

### Do now, before the next Scorecard run

1. Done. [`SECURITY.md`](SECURITY.md) now carries the private-advisory URL
   (`https://github.com/Rovetown/mdcompose/security/advisories/new`), which is
   what the Security-Policy check's linking requirement wants. Confirm the check
   reaches 10 on the next `scorecard.yml` run.

### First release

2. Done, verifies at step 4. `release.yml` `build` job runs
   `actions/attest-build-provenance` over `dist/*` (job now has
   `id-token: write` and `attestations: write`), stages the bundle as
   `mdcompose.intoto.jsonl`, and the `github-release` job attaches it to the
   Release (assets are now listed explicitly, since the artifact download keeps
   the `dist/` subdirectory and `gh release create` rejects a directory arg).
   A SLSA `*.intoto.jsonl` scores 10 on Signed-Releases. Only runs on a stable
   tag; pre-releases get no GitHub Release. Nothing to verify until the first
   stable release lands the assets.
3. Done. Alpha dry run published `0.1.0a0` to TestPyPI, verified end to end:
   `release.yml` build -> attest -> TestPyPI, `pypi` and `github-release` jobs
   correctly skipped, `gh attestation verify` passed online and against the
   staged `mdcompose.intoto.jsonl`, clean-venv `pip install` works. Two bugs
   found and fixed on the way: `cz bump` left `uv.lock` stale (fixed in #12,
   `bump.yml` now relocks and amends before the tag push) and a deleted
   prerelease tag left commitizen unable to bound the next changelog (fixed by
   reverting the botched bump in #13).

### README (active, before the stable release)

The README should be good before `0.1.0` reaches PyPI, since `readme =
"README.md"` becomes the PyPI long description. Structure is agreed: lean
front-door, ~130 to 200 lines, `for-the-badge` style shields badges, near-zero
emoji, ASCII diagrams and trees (no mermaid, because PyPI does not render it),
HTML only for layout. Prose is neutral-dev, accessible to a non-expert without
dropping the technical terms.

Done: [`README.md`](README.md) written (from the v3 draft, demo GIF placed in Quickstart
rather than Highlights, since the GIF shows the flow the Quickstart walks
through), both drafts deleted, `scripts/check_ascii.py` exempts [`README.md`](README.md)
via a `SKIP_FILES` set (Decisions log below records it), reference-level detail
moved out to [`docs/concepts.md`](docs/concepts.md), and a logo added: `docs/assets/mdcompose-logo.svg`
in the centered header (replacing the `# mdcompose` text heading), referenced
by the same absolute `raw.githubusercontent.com/.../main/...` URL as the demo
GIF so it also renders on PyPI, and `docs/assets/**` excluded from the sdist in
`pyproject.toml` (`[tool.hatch.build]`, verified with a real `uv build`; the
wheel was never affected, it already only packages `mdcompose`). Badges use
`style=for-the-badge`, not `flat-square`. Not yet committed.

Still to finish:

- **Record the demo GIF.** Deliberately deferred, not blocking `0.1.0`: no
  time to set up the recording right now. The README's Quickstart spot now
  holds an italic text placeholder instead of a broken `<img>` tag, with a
  comment naming exactly what to restore once the GIF exists. Plan for when
  time allows: script an asciinema recording of the real flow (create a
  snippet file, `mdcompose init` with the picker, `mdcompose doctor` showing a
  clean then drifted state), convert with
  `agg demo.cast docs/assets/mdcompose-demo.gif`. Keep it short, roughly 15 to
  25 seconds, one clear take. Shot list to write first: exact commands, where
  to pause, terminal size and theme so it is re-recordable when output
  changes. `docs/assets/` already exists (holds the logo).
- **Verify the badges resolve** once `0.1.0` is on PyPI (the PyPI, pyversions,
  and scorecard badges 404 or show "unknown" until then).

### After the README, resume the release

4. Done. `bump.yml` ran with channel `stable`, `0.1.0a0` -> `0.1.0`, `v0.1.0`
   tagged, the `pypi` environment approved. `v0.1.0` is live on PyPI and the
   first GitHub Release exists with the SBOM and attestation assets attached.
5. Done. [`CHANGELOG.md`](CHANGELOG.md)'s `## v0.1.0` entry replaced cz's thin
   auto body ("break the cli and command import cycle", "relock uv.lock",
   etc., none of which belong in a *user-facing* changelog) with "Initial
   public release." plus the full `### Added` command list restored verbatim
   from the old `[Unreleased]` section (recovered from commit `2252051`, since
   the alpha bump had already consumed it) and the `### Security`
   SLSA-provenance note. cz's `### Changed` and `### Fixed` sections dropped:
   there is no prior release to change from.

Also done in this pass, discovered from the live PyPI listing: the
`pypi/pyversions` badge showed a bare "Python 3" rather than the real
supported range, because shields.io reads PyPI's classifiers, not
`requires-python`, and only a bare `Programming Language :: Python :: 3` was
listed. `pyproject.toml` now lists `3.11` through `3.14` individually,
matching the CI matrix. This only takes effect on the *next* release; it does
not retroactively fix the metadata already published for `0.1.0`.

### After the first release

6. **Post-release hardening.** Partly done: `Development Status` moved to
   `4 - Beta` (the v1 feature set is complete and tested -- all 8 OpenSpec
   changes shipped, 93%+ coverage, mutation-tested, hardening review done --
   but pre-1.0 semver still allows a breaking change, so Beta fits better than
   a Stable claim; also takes effect on the next release only). Still open:
   point `platform.ONEDRIVE_HELP_URL` at a real page.
7. **OpenSSF Best Practices passing badge.** Register the repo at
   bestpractices.dev, complete the passing questionnaire (most criteria are
   already met by the existing CI, tests, license, and static analysis), embed
   the badge in the README. Scorecard's CII-Best-Practices check reads it
   through the API: 0 to 5. Silver and gold are not attainable for a
   solo-maintained project, so passing is the target. See [`docs/scorecard.md`](docs/scorecard.md).
8. **Dismiss the permanent Scorecard code-scanning alerts.** Code-Review,
   Branch-Protection, and Fuzzing are solo-maintainer structural or a
   deliberate non-goal (see [`docs/scorecard.md`](docs/scorecard.md), Accepted limitations). Dismiss
   them as "won't fix" in the Security tab so the alert count stays meaningful;
   leave Maintained and CII-Best-Practices to self-resolve.

### Not planned

9. **Fuzzing.** Left at 0. Scorecard does not detect Python Hypothesis, and an
   Atheris plus ClusterFuzzLite setup is out of proportion to the risk for two
   small parsers. Revisit only if the parser surface grows.

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

Excluded because metered or paid: Codecov, CodSpeed (CodSpeed has a free OSS
tier and is kept dormant, see below). Coverage is gated in-repo with
`coverage --fail-under` and uploaded as an artifact, never sent to a service.

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
`gitleaks`, `all-green`), `supply-chain.yml` (`licenses`, `audit`, `osv`,
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

- `codspeed` job in `ci.yml` - ENABLE WHEN the repo exists and a CodSpeed
  project is connected. The benchmark suite is written; only the hosted runner
  is missing.
- all-contributors config - ENABLE WHEN the first outside contributor lands.

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

Codecov / CodSpeed / any metered service (cost); git-cliff / towncrier
(commitizen writes the changelog); release-please / python-semantic-release
(rejected, philosophy C is the model); a triage bot (issue volume); hatch-vcs /
`hatch version` / setuptools-scm (no version-derivation layer; `cz bump` writes
`version` directly); trufflehog as a hook or job (it is a one-time local
pre-publish run only).

## Open work

Things that are not behavior, so they carry no core-contract change.

- [ ] Add an optional funding link via `.github/FUNDING.yml` and a line in the README footer. Deferred at the maintainer's request.

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

## Repository and release setup (needs the repo)

Plan and rationale: [`docs/publishing.md`](docs/publishing.md). In-repo artifacts (`release.yml`,
[`CHANGELOG.md`](CHANGELOG.md), `renovate.json`, `codeql.yml`, `scorecard.yml`,
`python-eol.yml`, workflow `permissions`) are all in place; the CI/CD pipeline
section is the reference. What is left is account-side, roughly in order.

Status, 2026-09-10: every account-side item in this list is done. The repo is
public, the ruleset is active, `RELEASE_TOKEN` and both Actions environments
exist, both trusted publishers are registered, and `pre-commit.ci` is enabled.
The checkboxes below are kept for the record and are not re-ticked here. The
live remaining work is in the `Next` section at the top of this file.

- [ ] Immediately before making the repo public: run `trufflehog git file://.
  --only-verified` over the full local history, confirm clean. One time, local,
  never a hook or a job.
- [ ] Create `github.com/Rovetown/mdcompose` and push. Enable private
  vulnerability reporting (the CODE_OF_CONDUCT contact points at it), Dependabot
  alerts, and Dependabot security updates.
- [ ] Confirm whether `Rovetown` is a personal account or an organisation: an
  organisation needs a free `GITLEAKS_LICENSE` key for `gitleaks-action`, a
  personal account does not.
- [ ] Branch protection on `main`: require `all-green`, `supply chain / *`, and
  `CodeQL`; require one review; require the branch up to date; require linear
  history; block force-push. Allow the `bump.yml` token identity to bypass the
  push restriction.
- [ ] Create a fine-grained PAT (or GitHub App token) with `contents: write`,
  store as the `RELEASE_TOKEN` secret; `bump.yml` uses it so the tag push
  triggers `release.yml` and the bump commit clears branch protection.
- [ ] Register a PyPI pending publisher for `mdcompose` (owner `Rovetown`,
  repo `mdcompose`, workflow `release.yml`, environment `pypi`), and the same
  on TestPyPI.
- [ ] Add GitHub Actions environments `pypi` (required reviewer) and `testpypi`.
- [ ] Enable `pre-commit.ci` on the repo and delete the `hooks` job from
  `ci.yml` (run one, not both).

Post-repo, at the release that earns it:

- [x] Move the `Development Status` classifier off `3 - Alpha`. Done: moved to
  `4 - Beta` (see the `Next` section above for the reasoning).
- [ ] Add a new Python to the CI matrix by hand when its first release
  candidate lands (annual, not worth a regex manager).
- [ ] Point `platform.ONEDRIVE_HELP_URL` (`https://mdcompose.dev/onedrive`) at a
  real how-to-exclude video before the first release.
- [ ] Wire the CodSpeed `benchmarks` job once the repo is up (it is written,
  just commented).
- [ ] Optional: write up the OneDrive warning in [`docs/core-contract.md`](docs/core-contract.md) if the
  project keeps that discipline post-v1. Implemented directly for now.

## Roadmap (later)

Everything here is a later, larger effort. The codebase-wide quality pass is
done: strict typing enforced in CI, a ratcheting coverage floor with its own
job, a benchmark suite with a recorded baseline, the file-I/O hardening review
and parser fuzzing. `platform.py` and the interactive questionary pickers in
`init` and `import` are the accepted remaining coverage gap; their flag paths
are fully covered.

### Agent skill composition (Claude Code Skills and equivalents)

Not scoped. Raised during the README rewrite as a marketing point worth
having a real backing plan for, not yet an OpenSpec change.

- [ ] Explore composing a project's agent-skill files the same way AGENTS.md
  and CLAUDE.md are composed today: a personal library of reusable skills,
  picked per project instead of an agent loading every skill unconditionally.
  A skill (a `SKILL.md`-shaped file: frontmatter plus a body, occasionally a
  script alongside it) is already close enough to a snippet in shape that the
  existing managed-block-and-manifest machinery may extend to it directly
  rather than needing a second mechanism.
- [ ] The actual argument for doing this, not just the organizational one:
  every skill an agent does not need loaded for a given project is context it
  never has to spend, so a curated per-project skill selection is a
  token-efficiency win. That is the pitch in the README and
  [`docs/concepts.md`](docs/concepts.md); it has to survive contact with a real design before it
  becomes more than a pitch.
- [ ] Revisit once v1 (AGENTS.md/CLAUDE.md composition) is stable. A second
  composed-file family is exactly the kind of expansion that has to prove it
  reuses the existing core rather than forking it, the standing bar for
  everything in this Roadmap section.

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

### Third-party integrations

- [ ] Research and, where practical, build integrations that let a user manage their content and snippet library without leaving their usual environment. Candidates are a VS Code extension or a JetBrains plugin; the TUI is tracked separately above. Before building anything new, evaluate whether extending an existing tool in this space is a better use of effort than duplicating config-sync mechanics that are already solved, so the focus stays on the snippet library and composition workflow that is not well covered elsewhere.

### Additional language implementations

- [ ] Once v1 behavior is stable and [`docs/core-contract.md`](docs/core-contract.md) is complete, port the CLI to one or more additional languages. Node.js/TypeScript, Go and Rust are the likely candidates. Broader than the zero-install binary below: this is about giving people who prefer not to touch Python a native option, not only about removing a runtime dependency. The contract exists so a port reimplements a specification rather than translating Python.

### Standalone binary distribution (zero install)

- [ ] Once behavior and file formats are stable, evaluate a zero-install path so end users need no Python. Candidates are PyInstaller or Nuitka, both trading binary size for no runtime dependency. If a port lands in Go or Rust, prefer shipping the binary from that instead: smaller static binaries, better cross-compilation, and a natural fit for Homebrew, Scoop, WinGet or an install script.

### Final naming verification before public release

- [ ] `mdcompose` was checked by search only. Before claiming it, run the exact checks: confirm `https://pypi.org/project/mdcompose/` returns 404, confirm `npm view mdcompose` errors, and register the GitHub repository before someone else does.

### Competitive landscape follow-up

- [ ] Periodically revisit how the tools listed above evolve, to confirm this project's differentiation stays genuine rather than duplicated.
