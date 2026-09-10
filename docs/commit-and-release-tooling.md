# Commit, versioning, changelog, and secret-scanning tooling

Research for the automation layer that goes in before the repo is public:
enforce Conventional Commits, produce a changelog per release, bump the version
by SemVer, keep secrets out, and make every file pass every check locally, not
only in CI.

Stars and dates are as of the 2026-09-09 survey.

## Summary of picks

| Concern | Pick | Runner-up | Avoid for this project |
| --- | --- | --- | --- |
| Hook framework | **pre-commit** | lefthook | husky (needs Node) |
| Commit-message enforcement | **commitizen** (`cz check`) | commitlint | gitlint (weaker preset) |
| Version + changelog + release | **commitizen** (`cz bump`, dispatched) | -- (none pursued) | python-semantic-release, release-please (both replace commitizen's role) |
| Secret scanning, local | **gitleaks** | detect-secrets | trufflehog as a hook (it is a one-time local pre-publish run) |
| Secret scanning, hosted | **GitHub native + push protection** | -- | -- |
| Workflow security lint | **zizmor** + **actionlint** (security + syntax) | -- | -- |
| Issue intake | GitHub issue forms + PR template | -- | a triage bot, at this size |

The stack is: `pre-commit` runs `commitizen` (`cz check`), `ruff`, `gitleaks`,
`zizmor`, `actionlint`, `check-github-workflows`, the ASCII check, and the
standard hygiene hooks. `commitizen` also owns the version bump and the
changelog, triggered from a `workflow_dispatch` action (`bump.yml`) that is the
release button; the existing `release.yml` publishes on the tag it creates.

## 1. Hook framework

### pre-commit  (winner)

- https://pre-commit.com/ , https://github.com/pre-commit/pre-commit  (15.6k)
- Python-native config (`.pre-commit-config.yaml`), runs hooks in any language
  in isolated environments it manages.
- Adoption: CPython, Django, pandas, pytest, scikit-learn, NumPy. It is the
  default for Python.
- `pre-commit.ci` ( https://pre-commit.ci/ ) runs the hooks on every PR, pushes
  auto-fixes back to the branch, and opens a weekly PR bumping hook versions.
  Free for public repos.
- `pre-commit-uv` ( https://github.com/tox-dev/pre-commit-uv ) makes it install
  hook environments with uv, which is much faster.
- Editable: one file, one `pre-commit autoupdate` command.

### Alternatives

- **lefthook** ( https://github.com/evilmartians/lefthook , 6k) - Go, single
  binary, faster on large repos, YAML config. Smaller hook ecosystem, no
  equivalent of pre-commit.ci. Fine, but you give up the ecosystem for speed
  this project does not need.
- **husky** ( https://github.com/typicode/husky , 33k) - JS only, requires a
  Node toolchain. Wrong ecosystem for a pure-Python package.

**Verdict: pre-commit. No real contest for Python.**

## 2. Commit-message enforcement (Conventional Commits)

Spec: https://www.conventionalcommits.org/en/v1.0.0/

| Tool | Lang | Scope | Stars | Notes |
| --- | --- | --- | --- | --- |
| **commitizen** | Python | check + prompt + bump + changelog | 3.5k | one tool for the whole lifecycle; config in `pyproject.toml` |
| commitlint | Node | check only (Angular's linter) | 18.7k | the JS standard; needs Node locally or a container/action |
| conventional-pre-commit | Python | check only, pure-Python hook | 549 | zero-dependency, does one thing |
| gitlint | Python | general commit linting | 750 | conventional-commits is not the default ruleset |

- **commitizen** ( https://commitizen-tools.github.io/commitizen/ ,
  https://github.com/commitizen-tools/commitizen ): `cz commit` is an
  interactive prompt that writes a conforming message; `cz check` validates a
  message or a commit range and is what runs in the `commit-msg` pre-commit
  stage and in CI ( `commitizen-tools/commitizen-action` , or
  `cz check --rev-range origin/main..HEAD` ).
- **commitlint** ( https://commitlint.js.org/ ,
  https://github.com/conventional-changelog/commitlint ): the reference
  implementation of Conventional Commits linting, used by Angular, Nx, most of
  the JS world. `@commitlint/config-conventional` is the ruleset everyone
  copies. CI is trivial ( `wagoid/commitlint-github-action` ); the local hook
  needs Node, or you run `conventional-pre-commit` locally and `commitlint`
  only in CI.

**Verdict: commitizen**, because it is Python, lives in `pyproject.toml`, and
the same tool does the version bump and the changelog, so there is one config
and one mental model. Choose commitlint only if you want the exact Angular
ruleset or already run Node tooling.

## 3. Versioning, changelog, and release automation

SemVer: https://semver.org/spec/v2.0.0.html . Keep a Changelog:
https://keepachangelog.com/en/1.1.0/

The field has four philosophies. **This project uses C.** A, B, and D are
recorded here as the alternatives that were considered and rejected.

### C. Commit-driven, you run the bump - commitizen `cz bump`  (chosen)

- https://commitizen-tools.github.io/commitizen/commands/bump/
- `cz bump` reads the commits, bumps the version in `pyproject.toml` (and
  anywhere else you configure), regenerates `CHANGELOG.md` from a template you
  own, and creates the tag. Run it from a `workflow_dispatch` action
  (`bump.yml`), which is itself the human gate.
- **Pro**: full control; the same tool already does `cz check` and `cz commit`,
  so one config and one mental model; the changelog template is editable Jinja;
  no surprise releases; `cz bump --dry-run` shows the next version and changelog
  first.
- **Con**: you have to press the button. For a solo project that is a feature.
- **Chosen** because commitizen is already the commit-message tool, so bump plus
  changelog plus tag in the same tool costs nothing extra, and the
  `workflow_dispatch` trigger is the review step a solo maintainer needs.

### A. Commit-driven, fully automatic - python-semantic-release  (rejected)

- https://python-semantic-release.readthedocs.io/
- On merge to `main`: computes the SemVer bump from the commits, writes the
  version and changelog, tags, publishes. Zero manual step.
- Rejected: it *replaces* commitizen's bump role rather than complementing it,
  and it removes the human gate - a commit typed `feat:` when it should be
  `fix:` ships a wrong minor, and undoing a bad auto-release means yanking from
  PyPI. Fully-automatic on-merge releases are out of scope for this project.

### B. Commit-driven, human-gated release PR - release-please  (not pursued)

- https://github.com/googleapis/release-please  (Google-maintained)
- A bot keeps one open "chore: release X.Y.Z" PR that accumulates the changelog
  and bump; merging it tags and publishes.
- Not pursued: a second bot and PR to maintain, needs a GitHub App or a PAT with
  write scope, and it duplicates the bump-and-changelog role `cz bump` already
  fills. The `bump.yml` button is the simpler gate.

### D. Explicit news fragments, not commits - towncrier  (dropped)

- https://towncrier.readthedocs.io/
- A human-written fragment file per PR, assembled into `CHANGELOG.md` at
  release. Independent of commit-message discipline; the format conservative
  Python projects trust.
- Dropped by decision: a file per PR is friction, it does not touch the version,
  and the payoff scales with the number of outside contributors, currently zero.
  Commit subjects enforced by `cz check` are the changelog source. Revisit only
  if contributors arrive and per-PR reviewed changelog lines become valuable.

### Also: semantic-release (JS)

- https://github.com/semantic-release/semantic-release - the JS standard.
  Plugin-based, second-class for Python. No reason to pick it over C.

### Verdict

**commitizen `cz bump`, dispatched from `bump.yml` = philosophy C.** One tool
for check, commit, bump, and changelog; config in `pyproject.toml`; the
changelog template is yours; releasing is a button. `release.yml` publishes on
the tag `cz bump` pushes. A, B, D, and semantic-release are rejected; the
decision is closed. No version-derivation layer (`hatch-vcs`, `setuptools-scm`)
is used - `cz bump` writes `version` in `pyproject.toml`.

Dedicated changelog generators (git-cliff, git-chglog) are not adopted:
`cz bump` writes the changelog in the same step as the bump, so a separate
binary and config file buys only output polish a solo pre-1.0 project does not
need.

## 4. Secret scanning

### Hosted: GitHub secret scanning + push protection  (primary)

- https://docs.github.com/en/code-security/secret-scanning/about-secret-scanning
- Free for public repos, zero config, and push protection blocks the commit at
  `git push` before the secret ever lands. This is the first line and needs
  nothing but a settings toggle.

### Local and CI: gitleaks  (winner among the scanners)

- https://github.com/gitleaks/gitleaks  (29k), Go, single binary.
- Regex plus entropy detection, a large built-in rule set, `.gitleaksignore`
  for the rare false positive, no baseline file to regenerate.
- pre-commit hook: `repo: https://github.com/gitleaks/gitleaks`. CI:
  `gitleaks/gitleaks-action`.

### Alternatives

- **detect-secrets** ( https://github.com/Yelp/detect-secrets , 4.6k) - Python,
  Yelp. Uses a committed `.secrets.baseline` you regenerate whenever findings
  change; audit-oriented; last release April 2026, slower cadence. More
  ceremony to maintain than gitleaks.
- **trufflehog** ( https://github.com/trufflesecurity/trufflehog , 20k) -
  verifies a candidate secret is live by calling the provider. Excellent for a
  one-time sweep of the full history before going public; heavier than you want
  on every commit.

### Verdict

Enable **GitHub native secret scanning + push protection** on the repo (a
settings toggle, no file). Add **gitleaks** as a pre-commit hook and a CI job:
the hook scans the staged diff, the CI job scans full history on every push and
PR.

**trufflehog: one time, locally, before the repo is public.** Run
`trufflehog git file://. --only-verified` over the entire history immediately
before pushing the repo public, confirm it is clean, then never run it again. It
is not a hook and not a CI job - it verifies candidate secrets by calling the
provider, too heavy and too networked for every commit. This run is a required
pre-publish checklist item (see `TODO.md`).

**detect-secrets** is not used: its committed `.secrets.baseline`, regenerated
whenever findings change, is more ceremony than gitleaks' inline
`.gitleaksignore` for no additional coverage here.

## 5. "Every file passes every check" - the pre-commit config

Hooks to include, each with why:

| Hook | Source | Why |
| --- | --- | --- |
| `trailing-whitespace`, `end-of-file-fixer`, `mixed-line-ending` | pre-commit/pre-commit-hooks | trivial diffs and cross-platform line endings, caught before commit |
| `check-yaml`, `check-toml`, `check-json` | same | a broken workflow or `pyproject.toml` cannot be committed |
| `check-added-large-files` | same | no accidental binary or data file |
| `check-merge-conflict` | same | no `<<<<<<<` markers |
| `ruff check` (`--fix`) | astral-sh/ruff-pre-commit | the project already lints with ruff; run it before commit, not only in CI |
| ASCII check | local hook (`language: python` or `pygrep`, so pre-commit.ci can run it) | currently only in CI; mirror it so the plain-ASCII rule fails locally |
| `cz check` | commitizen | the commit message conforms, at `commit-msg` stage |
| `gitleaks` | gitleaks/gitleaks | no secret in the diff |
| `zizmor` | https://github.com/woodruffw/zizmor | lints GitHub Actions for the exact issues OpenSSF Scorecard grades: unpinned actions, over-broad `permissions`, injectable `${{ }}` in `run` |
| `actionlint` | https://github.com/rhysd/actionlint | workflow syntax and `run:` shell errors, which zizmor does not check |
| `check-github-workflows` | pre-commit/pre-commit-hooks (via `check-jsonschema`) | workflow files validate against the GitHub Actions schema |

zizmor and actionlint are complementary, not alternatives: zizmor is the
security posture, actionlint is syntax and shell. Both run as hooks, so neither
needs a separate workflow.

### pre-commit, pre-commit-uv, pre-commit.ci - no conflicts between them

- **pre-commit** is the framework and the `.pre-commit-config.yaml`.
- **pre-commit-uv** ( https://github.com/tox-dev/pre-commit-uv ) makes
  `pre-commit` build its hook environments with uv instead of pip and
  virtualenv. It is a **local-dev speed-up only**, enabled by installing it
  alongside pre-commit (`uv tool install pre-commit --with pre-commit-uv`). It
  changes no hook output, and pre-commit.ci ignores it. No conflict.
- **pre-commit.ci** ( https://pre-commit.ci/ ) is a hosted GitHub App that runs
  the same `.pre-commit-config.yaml` on every PR, pushes auto-fixes back, and
  opens a weekly hook-autoupdate PR. Free for public repos. It is a *runner*,
  not a competing tool. **One rule: run the self-hosted `hooks` CI job OR
  pre-commit.ci, never both.** Plan: a plain `pre-commit run --all-files` job
  until the repo is public, then switch to pre-commit.ci. A hook that genuinely
  cannot run there (needs Docker, a private binary) goes in the config's
  `ci: skip:` list.

## 6. Issue and PR intake

Do the first three at repo-public time. GitHub-native, no tooling. Skip the
triage bot.

- [ ] `.github/ISSUE_TEMPLATE/bug_report.yml` and `feature_request.yml` as
  **issue forms** ( https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository ):
  structured YAML fields, GitHub renders them.
- [ ] `.github/ISSUE_TEMPLATE/config.yml` with `blank_issues_enabled: false` and
  a contact link pointing questions to GitHub Discussions.
- [ ] `.github/PULL_REQUEST_TEMPLATE.md` with the CONTRIBUTING checklist inline.
- Triage bot (`actions/stale`, `dessant/label-actions`): **not used.** Issue
  volume will not justify it at this size, and auto-closing a solo project's
  stale issues is user-hostile.
