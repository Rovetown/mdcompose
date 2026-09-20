# CI/CD pipeline

The final plan. It is meant to be trusted and left alone: every workflow, its
trigger, its cost, and the two non-obvious wrinkles (`bump.yml` needs a PAT;
branch protection needs a bypass for it) are spelled out.

## Cost - all free

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

## Principles

- One workflow file per concern; each declares its own minimal `permissions`,
  and a failure names the concern.
- Every workflow gets a `concurrency` group keyed on the ref, cancelling
  superseded runs on the same branch. `ci.yml` is the exception for pushes; see
  "Skipping work for documentation-only changes".
- Every job sets `timeout-minutes`.
- Actions pinned to a full commit SHA; Renovate's
  `helpers:pinGitHubActionDigests` does the first pin and keeps them current.
- One `all-green` gate job (`needs:` every other `ci.yml` job) so branch
  protection requires one check, not twelve matrix legs.

## Workflows - final list

In the repo now: `ci.yml` (test matrix 3 OS x Python 3.11-3.14, `lint` (ruff +
`mypy` + `deptry`), `coverage`, `ascii`, `build`, plus `hooks`, `commits`,
`gitleaks`, `benchmarks` (CodSpeed, not in `all-green`'s needs), `all-green`),
`supply-chain.yml` (`licenses`, `audit`, `osv`,
`sbom`), `dependency-review.yml` (PR-only, `deny-licenses` = the copyleft
families), `release.yml` (`v*` tag), `bump.yml` (the dispatched release button),
`mutation.yml` (weekly `mutmut`), `codeql.yml`, `scorecard.yml`,
`python-eol.yml`. `.pre-commit-config.yaml` carries a `ci:` block for
pre-commit.ci. [`SECURITY.md`](../SECURITY.md) points at private vulnerability reporting.

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

## Skipping work for documentation-only changes

A change that only touches documentation or images does not need the test
matrix, so the expensive jobs are skipped for it. The mechanism differs per
workflow because of one rule: a workflow skipped by a trigger-level path filter
reports no checks at all, and branch protection would wait forever on a required
check that never arrives.

- **`ci.yml` decides per job.** A `changes` job diffs the run against its base
  (the pull request base, or the commit before a push) and outputs `code=true`
  unless every changed file is under `docs/`, ends in `.md`, or is
  `.github/FUNDING.yml` or an issue template. Everything else counts, `LICENSE`
  included, because `pyproject.toml` ships it in the wheel and sdist. `test`, `lint`,
  `coverage`, `build`, `workflows`, and `benchmarks` need it and run only when
  `code` is true. `ascii`, `gitleaks`, and `commits` always run, so Markdown is
  still checked for non-ASCII characters and secrets. `all-green` always runs
  and treats a skipped job as passing, so the required check reports on every
  pull request and push. Anything unexpected counts as a code change: a manual
  run, a first push, or a base commit that cannot be found. A failing `git diff`
  fails the job rather than reading as "no code changed".
- **`codeql.yml` and `scorecard.yml` filter the push trigger only** with
  `paths-ignore` for `docs/**` and `**/*.md`. Their pull request runs are
  unfiltered because `CodeQL` is a required check.
- **`supply-chain.yml` runs on push only when `pyproject.toml`, `uv.lock`,
  `scripts/check_licenses.py`, or the workflow itself changes.** That is the
  list its pull request trigger already used. The weekly cron catches
  advisories that land in between.

Consequences to know about:

- `ci.yml` no longer cancels a running push when another push arrives. Its
  concurrency group is per commit for pushes and per pull request number for
  pull requests. Otherwise a docs-only push would cancel the tests of the code
  push before it, and its own run would skip them, leaving that code unverified.
- A release still runs everything: the `bump.yml` commit changes
  `pyproject.toml`, so `code` is true.
- Only `all green`, `analyze python`, and `dependency review` are required
  checks. `ci.yml` never path-filters its triggers, `codeql.yml` does not filter
  its pull request run, and `dependency-review.yml` has no filter, so every
  required check reports on every pull request, docs-only included.
  `supply-chain.yml` is filtered on pull requests but is not required.

## The `bump.yml` PAT wrinkle (important)

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

## Dormant - shipped commented, with an `# ENABLE WHEN:` marker

- all-contributors config - ENABLE WHEN the first outside contributor lands.

The `benchmarks` job in `ci.yml` was in this list; it is now uncommented,
pinned, and connected at codspeed.io (run `34781861376`, commit `4b43aa5`,
2026-09-13, uploaded successfully after an earlier run failed with a
`401 Unauthorized` before the account-side connection existed). It runs on
every push and PR but is not in `all-green`'s needs list, so it cannot block a
merge.

(`mutation.yml` is not dormant - it ships active on a weekly cron, non-blocking.)

## Local iteration

`act` (https://github.com/nektos/act) runs the workflow files in Docker without
pushing - use it for `bump.yml` and the `ci.yml` jobs. It does not emulate
OIDC, environments, or Trusted Publishing, so `release.yml` is still validated
for real on a tag against TestPyPI.

## pre-commit: framework vs accelerator vs runner - no conflicts

- `pre-commit` is the framework and `.pre-commit-config.yaml`.
- `pre-commit-uv` builds hook envs with uv; local-dev speed only, installed
  alongside pre-commit, changes no output, pre-commit.ci ignores it.
- `pre-commit.ci` is a hosted App that runs the same config on PRs, auto-fixes,
  autoupdates weekly. A runner, not a competitor. Run the `hooks` job **or**
  pre-commit.ci, never both.

## Branch protection (the `main` ruleset, checked 2026-09-20)

The repository ruleset named `main` is active. It requires a pull request
(squash or rebase merge, zero required approvals), linear history, and no
deletion or non-fast-forward updates. Its required status checks, with the
branch required to be up to date, are exactly three: `all green`,
`analyze python` (the CodeQL job), and `dependency review`. The `supply chain`
jobs are not required checks. The repository owner is the only bypass actor
(bypass mode always), which is what allows a direct push to `main`. Dependabot
alerts and security updates and private vulnerability reporting are enabled.
The `bump.yml` token identity must stay a bypass actor for the release commit.

## Release flow, end to end

1. Conventional Commits land on `main` (enforced by the `commits` job and the
   `cz check` hook).
2. Run `bump.yml` from the Actions tab; pick stable or a prerelease channel.
   `cz bump` writes the version and changelog, commits, pushes `vX.Y.Z` with the
   PAT.
3. `release.yml` fires on the tag: build, check, SBOM, then TestPyPI, then
   (stable tags only) PyPI behind the `pypi` reviewer, then the GitHub Release.
4. Between releases: Renovate and Dependabot keep dependencies and pinned SHAs
   current; CodeQL, Scorecard, and `python-eol.yml` run on their schedules.

## Explicitly not in the pipeline

Codecov / any other metered service (cost); git-cliff / towncrier
(commitizen writes the changelog); release-please / python-semantic-release
(rejected, philosophy C is the model); a triage bot (issue volume); hatch-vcs /
`hatch version` / setuptools-scm (no version-derivation layer; `cz bump` writes
`version` directly); trufflehog as a hook or job (it is a one-time local
pre-publish run only).
