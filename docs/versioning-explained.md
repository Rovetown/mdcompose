# How automated versioning and releases actually work

The question this answers: in an action, how does `0.3.1` become `0.3.2` or
`0.4.0` or `1.0.0`, and where do `alpha` / `beta` / `rc` fit? The short answer
is that you almost never type the number. A tool derives it from the commit
history since the last tag, and you only choose the *kind* of release
(stable vs pre-release) and *when* to press the button.

## 1. The version number itself

### SemVer 2.0 - `MAJOR.MINOR.PATCH`

https://semver.org/spec/v2.0.0.html

Three segments, each an integer, meaning:

- **PATCH** (`0.3.1 -> 0.3.2`): a backward-compatible bug fix. Nothing a user
  calls behaves differently on purpose.
- **MINOR** (`0.3.2 -> 0.4.0`): a backward-compatible new feature. Old usage
  still works; there is more it can now do. PATCH resets to 0.
- **MAJOR** (`0.4.0 -> 1.0.0`): a breaking change. Old usage may stop working.
  MINOR and PATCH reset to 0.

`0.x` is special: while MAJOR is 0 the project is declaring "anything may
change". Many tools treat a breaking change under `0.x` as a MINOR bump
(`0.4.0 -> 0.5.0`), not a jump to `1.0.0`, because reaching `1.0.0` is a
deliberate "the API is now stable" statement, not an automatic consequence.

There is **no fourth segment**. `1.2.3.4` is not SemVer. If you see it, it is
usually one of:

- a Python post-release, `1.2.3.post1` (see PEP 440 below): a packaging-only
  re-release with no code change, e.g. you fixed the README or the wheel
  metadata.
- a vendor scheme (`.NET`, some enterprise Java) that predates SemVer.
- a project that conflates "build number" with "version". Avoid it; use build
  metadata (`1.2.3+build.42`) or a post-release instead.

### Pre-releases - `alpha`, `beta`, `rc`

A pre-release is a version that sorts *before* the stable one with the same
`MAJOR.MINOR.PATCH`. SemVer writes it with a hyphen and dot-separated
identifiers:

    1.0.0-alpha.1  <  1.0.0-alpha.2  <  1.0.0-beta.1  <  1.0.0-rc.1  <  1.0.0

Convention, not enforced by the spec:

- **alpha**: feature-incomplete, expect breakage, for early testers.
- **beta**: feature-complete for this version, still finding bugs.
- **rc** (release candidate): believed shippable; becomes the stable release
  unchanged if nothing blocks it.

You do not have to use all three, or any. A common minimal flow is: cut
`1.0.0-rc.1`, let it sit a week, promote to `1.0.0`.

### PEP 440 - Python's version spec, which is *not* SemVer

https://peps.python.org/pep-0440/

PyPI and pip validate against PEP 440, not SemVer. The core
`MAJOR.MINOR.PATCH` is the same, but the extras differ in spelling:

| Meaning | SemVer | PEP 440 |
| --- | --- | --- |
| alpha 1 | `1.2.0-alpha.1` | `1.2.0a1` |
| beta 2 | `1.2.0-beta.2` | `1.2.0b2` |
| release candidate 1 | `1.2.0-rc.1` | `1.2.0rc1` |
| post-release 1 | (build metadata) | `1.2.0.post1` |
| dev build 5 | (not expressible) | `1.2.0.dev5` |
| local build tag | `1.2.0+abc123` | `1.2.0+abc123` |
| epoch (reset scheme) | (none) | `1!2.0.0` |

Two consequences:

- A tool aimed at Python (`commitizen`, `python-semantic-release`,
  `hatch-vcs`) emits PEP 440 by default (`1.2.0a1`). A tool aimed at the wider
  world (`release-please`, `semantic-release`) emits SemVer (`1.2.0-alpha.1`);
  for a Python project it has to be configured to write PEP 440 into
  `pyproject.toml`.
- `pyproject.toml` currently carries `version = "0.1.0.dev0"`. That is a valid
  PEP 440 dev-release: "the zeroth dev build heading toward 0.1.0". It sorts
  before `0.1.0a1`.

### CalVer - the alternative to SemVer

https://calver.org/

Version is the date: `2026.9`, `26.09.1`, `2026.9.14`. Used by pip
(`24.0`), Ubuntu, Black (`24.1.0` is `YY.MM.patch`), pytz. Right when
"how old is this" matters more than "will this break me", or when every
release is a mixed bag with no single semantic. Wrong for a library whose
users pin ranges and need to reason about compatibility. mdcompose is a
library-shaped CLI, so SemVer (PEP 440 spelling) fits.

`ZeroVer` ( https://0ver.org/ ) is the joke-but-real practice of staying on
`0.x` forever. Fine as a deliberate "no stability promise yet"; a decision to
make, not a default to drift into.

## 2. How a tool decides the bump

Every conventional-commit-driven tool does the same thing: read the commits
between the last version tag and `HEAD`, map each to a bump level, take the
highest.

| Commit | Bump | Example |
| --- | --- | --- |
| `fix: ...` | PATCH | `0.3.1 -> 0.3.2` |
| `perf: ...` | PATCH (tool-configurable) | |
| `feat: ...` | MINOR | `0.3.2 -> 0.4.0` |
| `feat!: ...` or a `BREAKING CHANGE:` footer | MAJOR (MINOR under `0.x` for most tools) | `0.4.0 -> 1.0.0` or `0.4.0 -> 0.5.0` |
| `docs:`, `test:`, `chore:`, `ci:`, `refactor:`, `style:`, `build:` | none | no release |

So the version is a pure function of what landed. You control it by writing
the right commit type, which is exactly what `commitizen`'s `cz check` and the
pre-commit hook enforce. A run with only `docs:` and `chore:` commits produces
no release at all, which is the correct behavior.

The `!` and the `BREAKING CHANGE:` footer are the only way to force a MAJOR:

    feat!: drop the --agents-from flag

    BREAKING CHANGE: --agents-from is removed; use `import --to-claude` instead.

## 3. How pre-releases are triggered

The bump level (patch/minor/major) is automatic. The *channel* (stable vs
alpha/beta/rc) is a choice you pass in. Three common ways:

### A. A workflow input  (this is what `.github/workflows/bump.yml` does)

A `workflow_dispatch` with a `prerelease` choice input:

    on:
      workflow_dispatch:
        inputs:
          prerelease:
            type: choice
            default: stable
            options: [stable, alpha, beta, rc]

    # then, in the job (channel passed through an env var, never interpolated
    # into the shell):
    #   if channel == stable:  cz bump --yes --changelog
    #   else:                  cz bump --yes --changelog --prerelease "$PRERELEASE"

The option is `stable` rather than an empty string because GitHub Actions
rejects an empty choice value. `cz bump --prerelease beta` turns `0.4.0` (the
level the commits imply) into `0.4.0b1`, then `0.4.0b2` on the next run, then
`cz bump` with the `stable` channel promotes `0.4.0b2` to `0.4.0`.

### B. A release branch

`main` publishes stable. A long-lived `next` or `rc` branch publishes
pre-releases: the same tool runs there with `--prerelease rc` (or, in
`python-semantic-release`, a branch config that sets the pre-release token).
Merging `next` into `main` and running there cuts the stable release.

### C. Tag shape

You (or the tool) push `v1.0.0-rc.1` vs `v1.0.0`. `release.yml` already fires
on any `v*` tag; add a step that marks the GitHub Release as a pre-release and
tells `pypa/gh-action-pypi-publish` nothing special is needed (PyPI accepts
`1.0.0rc1`; `pip install` ignores pre-releases unless `--pre` is passed, which
is the desired default).

### Recommended for mdcompose

Option A. One `release.yml` (already present, publishes on tag) plus a
`bump.yml` with a `workflow_dispatch` `prerelease` input that runs `cz bump`
and pushes the tag. Stable is the empty choice; alpha/beta/rc are the others.
You never type a number; you pick "release" or "release a beta" and press run.

## 4. The full automated release, end to end

1. Every PR: `pre-commit` and CI enforce Conventional Commits (`cz check`),
   style, ASCII, tests, no secrets.
2. Commits accumulate on `main` with correct types.
3. When you want to ship, run the `bump` action (choose stable or a
   pre-release channel).
4. `cz bump` reads the commits, computes the next PEP 440 version, rewrites
   `pyproject.toml` and `CHANGELOG.md`, commits that, and creates `vX.Y.Z`.
5. The tag push triggers `release.yml`: build, `twine check`, SBOM, publish to
   TestPyPI then PyPI via Trusted Publishing (no token, PEP 740 attestations),
   each behind a reviewed environment, then a GitHub Release with artifacts.
6. Renovate, `pip-audit`, CodeQL, and Scorecard keep the released package
   maintained between releases.

The only manual acts are: write good commit types (enforced), press the bump
button, and approve the two publish environments.

## 5. What each piece is responsible for

| Piece | Owns |
| --- | --- |
| Conventional Commits + `cz check` | the *input signal* for the version |
| `cz bump` (or PSR / release-please) | turning that signal into a number, a changelog entry, and a tag |
| `pyproject.toml` `version` (or hatch-vcs) | where the number is stored |
| `release.yml` | turning a tag into published artifacts |
| Trusted Publishing + attestations | proving the artifacts came from that workflow |
| Renovate / audits / scanners | the package's health after release |
