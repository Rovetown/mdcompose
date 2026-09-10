# Optional and adjacent tooling

Tools worth knowing about beyond the picks in
`docs/commit-and-release-tooling.md`. None is required.

Two views of the same catalogue:

1. **By fit for mdcompose** - the actionable view: adopt now, dormant, later, or
   never, with the reason.
2. **Quick index by job** - the reference view, for a "what are my options for
   X" lookup.

The baseline picks are decided in the other doc and not repeated in the fit
tables: `pre-commit`, `commitizen`, `gitleaks`, GitHub native secret scanning,
`zizmor`. `coverage.py` and `pytest-benchmark` are already in the roadmap
quality pass, so they appear below marked "(already planned)".

## By fit for mdcompose

Context that sets the tiers: solo maintainer, pure-Python CLI, pre-1.0, plain
ASCII enforced, a TUI planned as a later second adapter, no public repo yet,
release model is commitizen `cz bump` (philosophy C).

### Strong fit - adopt during the automation baseline or the quality pass

| Tool | Link | Job | Why it fits | Where it lands |
| --- | --- | --- | --- | --- |
| **mypy** | https://mypy-lang.org/ | static types | codebase is fully annotated and LBYL, so adoption is near-free; catches a real bug class; de-risks the TUI refactor | quality pass |
| **coverage.py** (`pytest-cov`) | https://coverage.readthedocs.io/ | test coverage | a floor keeps the TUI branch from silently dropping core coverage | quality pass (already planned) |
| **hypothesis** | https://hypothesis.readthedocs.io/ | property tests | `sections.parse_sections` and `managed_block.scan` are parsers over arbitrary markdown; feed garbage, assert invariants | quality pass, hardening |
| **pytest-benchmark** | https://pytest-benchmark.readthedocs.io/ | microbenchmarks | lock scanner performance before the TUI adds callers | quality pass (already planned) |
| **pytest-randomly** | https://github.com/pytest-dev/pytest-randomly | randomize test order | one line of config; catches inter-test state leaks | quality pass |
| **actionlint** | https://github.com/rhysd/actionlint | Actions syntax + shell lint | complements zizmor (syntax vs security); runs as a pre-commit hook | automation baseline, step 5 |
| **check-github-workflows** (`check-jsonschema`) | https://github.com/python-jsonschema/check-jsonschema | workflow schema validation | a malformed workflow cannot be committed | automation baseline, step 5 |
| **pre-commit-uv** | https://github.com/tox-dev/pre-commit-uv | faster hook installs | local-dev only; builds hook envs with uv; pre-commit.ci ignores it, no conflict | automation baseline, step 1 |
| **dependency-review-action** | https://github.com/actions/dependency-review-action | PR dependency gate | blocks a PR adding a vulnerable or non-permissive dependency; pairs with `scripts/check_licenses.py` | needs the repo |
| **Dependabot security updates** | https://docs.github.com/en/code-security/dependabot | vuln PRs | a repo toggle only, no `dependabot.yml` (that file is for version updates, which Renovate owns) | needs the repo |

### Useful - adopt now or keep dormant with an enable trigger

| Tool | Link | Job | Status |
| --- | --- | --- | --- |
| **osv-scanner** | https://google.github.io/osv-scanner/ | third vulnerability source over `uv.lock` | adopt: add to `supply-chain.yml` next to pip-audit and grype; the OSV.dev database aggregates advisories the other two can miss |
| **deptry** | https://github.com/fpgmaas/deptry | unused / missing / misplaced dependencies | adopt: run once now; add a CI job if it finds anything worth gating |
| **interrogate** | https://github.com/econchick/interrogate | docstring coverage gate | adopt during the quality pass if public `core/` functions must all be documented for a TUI or a language port |
| **codspeed** | https://codspeed.io/ | hosted benchmark tracking, instrumented so it is stable across runners | DORMANT: ship the job commented. ENABLE WHEN `pytest-benchmark` variance on the shared runner makes regressions unreadable. Free for open source |
| **mutmut** (or **cosmic-ray**) | https://mutmut.readthedocs.io/ | mutation testing: mutate the code, confirm a test fails - the honest measure of test quality, where coverage only measures reach | adopt: `mutation.yml` on a weekly (or monthly) cron plus `workflow_dispatch`, scoped to `core/`. Surfaces where freshly written code needs more tests. Reports only, never a required check - too slow to gate a PR (one suite run per mutant) |
| **all-contributors** | https://allcontributors.org/ | contributor credit in the README | DORMANT: ship the config commented. ENABLE WHEN the first outside contributor lands |

### Less useful now - real tools, wrong stage or redundant here

| Tool | Link | Why not now |
| --- | --- | --- |
| **bump-my-version / tbump** | https://github.com/callowayproject/bump-my-version | the version lives in one place; there is no multi-file bump problem, and `cz bump` does the write |
| **vulture** | https://github.com/jendrikseipp/vulture | a one-off pass during the quality sweep, not a standing gate on a small codebase |

### Removed from the shortlist as unnecessary for this project

`python-semantic-release` (fully-automatic on-merge releases; replaces the
`cz bump` model and removes the human gate - out of scope), `hatch-vcs` /
`hatch version` / `setuptools-scm` / `versioningit` / `dunamai` (tag-derived or
manual version tooling; `cz bump` writes `version` in `pyproject.toml` directly,
no version-derivation layer is used), `release-please` (a second release brain
next to commitizen), `cocogitto` (Rust; duplicates commitizen and adds a
binary), `release-drafter` (only useful with a PR-based release flow),
`MkDocs + Material` and `mkdocstrings` and `Sphinx` and `Read the Docs` (no docs
site planned; the README and `docs/` suffice), `ty` and `pyright` /
`basedpyright` (one type checker, mypy, is enough), `conventional-pre-commit`
(commitizen's `cz check` covers commit-message linting), `pinact` / `ratchet`
(Renovate's `helpers:pinGitHubActionDigests` pins action SHAs), `radon` /
`xenon` (the four-indent rule and small modules already bound complexity),
`Dependabot` version updates (Renovate owns version bumps; Dependabot *security*
updates are separate and kept), `towncrier` (removed by decision, see below).

### Wrong ecosystem or redundant - recorded only as considered

`semantic-release` (JS), `changesets` (JS monorepo), `release-plz` (Rust
crates), `knope` (replaces commitizen for no gain), `auto` (label-driven JS),
`git-cliff` / `git-chglog` (dedicated changelog generators; commitizen writes
the changelog), `sigstore` / `cosign` (PEP 740 attestations already cover a
pure-Python PyPI package), `reuse` (per-file SPDX headers, for projects that
vendor code), `bandit` (overlaps CodeQL's Python queries), `git-absorb` (a
personal git convenience, not project tooling).

### Decision: commitizen keeps the changelog, towncrier dropped

`cz bump` does the version bump, changelog, commit, and tag in one step from a
Jinja2 template the project controls. Dedicated changelog generators (git-cliff,
git-chglog) add a separate binary and config file for output polish a solo
pre-1.0 project does not need. `towncrier` (a human-written news fragment per
PR, assembled at release) was evaluated and dropped: its payoff scales with the
number of outside contributors, currently zero, and commit subjects enforced by
`cz check` are the changelog source. Revisit only if the commitizen template
cannot produce the Keep a Changelog format wanted, or if per-PR reviewed
changelog lines become valuable once contributors arrive.

### Decision: secret scanning is gitleaks plus GitHub native, and trufflehog once

`gitleaks` runs as a pre-commit hook (staged diff) and a CI job (full history on
every push and PR). GitHub native secret scanning and push protection are
enabled at repo-creation time. `trufflehog` runs **once, locally, over the full
history immediately before the repo goes public** (`trufflehog git file://.
--only-verified`), is confirmed clean, and is then never run again - it is not a
hook and not a CI job. `detect-secrets` is not used: its committed
`.secrets.baseline` is more ceremony than gitleaks' inline ignore for no added
coverage here.

## Quick index by job

- **Version storage / derivation**: none - `cz bump` writes `version` in
  `pyproject.toml` directly, no derivation layer
- **Release automation**: commitizen `cz bump` (pick, philosophy C)
- **Changelog**: commitizen (pick)
- **Actions security and hygiene**: zizmor (pick), actionlint,
  check-github-workflows
- **Dependency and vulnerability scanning**: pip-audit (in use), grype (in use),
  osv-scanner (adopt), dependency-review-action (needs repo), Dependabot
  security updates (needs repo)
- **Static types**: mypy (recommended)
- **Test quality and benchmarking**: coverage.py, hypothesis, pytest-benchmark,
  pytest-randomly, mutmut (`mutation.yml`, weekly cron, non-blocking),
  codspeed (dormant)
- **Dead code and docstrings**: deptry, vulture (one-off), interrogate
- **Contributor meta**: all-contributors (dormant)
