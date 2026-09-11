# OpenSSF Scorecard

Where the project stands on the OpenSSF Scorecard, and what is worth doing about it.
The action items live in [TODO.md](../TODO.md), in the `Next` section, sequenced with the rest of the release work.
This file is the reasoning behind them.

Live score: <https://scorecard.dev/viewer/?uri=github.com/Rovetown/mdcompose> Raw JSON: <https://api.scorecard.dev/projects/github.com/Rovetown/mdcompose>

Last reviewed: 2026-09-10, commit `0fe8e27`, overall score 6.5.

## Checks already at 10

Pinned-Dependencies, Token-Permissions, SAST, CI-Tests, License, Vulnerabilities, Binary-Artifacts, Dangerous-Workflow, Dependency-Update-Tool.
These need nothing.
Do not regress them.

## Gap table

| Check | Score | Verdict | Reason |
| ----- | ----- | ------- | ------ |
| Security-Policy | 4 | Fix now | [SECURITY.md](../SECURITY.md) has explanatory prose but no `https://` link or email, so the 6-point linking requirement is unmet. |
| Signed-Releases | not scored | Fix at first stable release | `release.yml` attaches only `dist/*` to the GitHub Release. No signature or provenance file, so the check has nothing to score. |
| Packaging | not scored | Resolves itself | Scorecard recognises `pypa/gh-action-pypi-publish`. The check flips to 10 after the first release runs. No work. |
| Maintained | 0 | Ignore, time heals it | Age penalty only: the repository is under 90 days old. Clears once it passes 90 days with regular commit or issue activity. |
| CII-Best-Practices | 0 | Medium priority | No OpenSSF Best Practices registration. A passing badge is worth 5 on this check. |
| Branch-Protection | 4 | Capped, accept | Scorecard treats `EnforceAdmins` as false whenever any ruleset bypass actor exists, and `bump.yml` needs the maintainer bypass. |
| Code-Review | 0 | Cannot fix | Needs approving reviews from someone other than the commit author. Single maintainer. |
| Contributors | 0 | Cannot fix | Needs contributors affiliated with two or more organisations. Single maintainer. |
| Fuzzing | 0 | Low value, skip | Scorecard does not detect Python Hypothesis. A libFuzzer or Atheris plus ClusterFuzzLite setup is disproportionate for a Markdown CLI with two small parsers. |

## Detail

### Security-Policy

Scorecard scores the policy in three parts: 6 points for a contactable link (an `https://` URL or an email address), 3 points for free-form explanatory text, 1 point for specific vulnerability and disclosure language.
The file already earns the last two.
It is missing a link.

Fix: add a line to [SECURITY.md](../SECURITY.md) pointing at `https://github.com/Rovetown/mdcompose/security/advisories/new`, the private advisory form.
That is the same channel the prose already describes, now in a form the check can see.
Result: 10.

### Signed-Releases

The check looks at the assets attached to the last several GitHub Releases for a signature file (`*.sig`, `*.asc`, `*.sigstore.json`, and similar) or a SLSA provenance file (`*.intoto.jsonl`, worth the full 10).
The PEP 740 attestations that `pypa/gh-action-pypi-publish` generates go to PyPI, not to the GitHub Release, so they do not count here.

Fix: add `actions/attest-build-provenance` to `release.yml` and attach its output to the `gh release create` asset list.
The `github-release` job then also needs `id-token: write` and `attestations: write` alongside its existing `contents: write`.
A `*.sigstore.json` bundle scores 8; a SLSA `*.intoto.jsonl` scores 10.

Pre-releases (`a1`, `b1`, `rc1`) never get a GitHub Release, so this only has to be in place before the first stable tag, not before the alpha.

### Packaging

Nothing to do. `release.yml` already publishes through `pypa/gh-action-pypi-publish`, which is on Scorecard's detection list.
The check reads `not scored` only because no release has run yet.

### Maintained

A repository younger than 90 days scores 0 regardless of activity.
After 90 days the score reflects commit and issue activity over the trailing period.
Regular work on the project is enough; nothing to build.

### CII-Best-Practices

Scorecard reads the OpenSSF Best Practices badge API and maps the tier to a score: in progress 2, passing 5, silver 7, gold 10.

A passing badge is realistic.
Most of its criteria are already satisfied by the existing CI, test suite, MIT license, CodeQL, pinned dependencies, and [SECURITY.md](../SECURITY.md).
The work is registering the project at bestpractices.dev, completing the self-assessment, and embedding the badge in the README.

Silver and gold are not attainable for a solo-maintained project.
Both require `contributors_unassociated` (two or more significant contributors who are not affiliated with the same organisation) and `bus_factor` above one, and both are MUST criteria.
Passing is the target.

### Branch-Protection

The remaining warnings (no required approvers, no CODEOWNERS review, no stale review dismissal, no last-push approval, admin enforcement off) all reduce to two things: the project requires no reviews because it has one maintainer, and the ruleset grants that maintainer a bypass so `bump.yml` can push the release commit and tag.
Scorecard's documented behaviour is to score `EnforceAdmins` as false whenever any bypass actor exists on any rule.

Requiring one review and adding a CODEOWNERS file would raise the check, but then every merge needs the bypass, which defeats the point of the rule.
The score of 4 is the accepted ceiling.

### Code-Review and Contributors

Both measure multi-person process: Code-Review wants merged changes approved by someone other than the author, Contributors wants people from more than one organisation.
Neither is achievable with one maintainer.
Accepted.

### Fuzzing

Scorecard recognises Go native fuzzing, OSS-Fuzz, ClusterFuzzLite, and a short list of property-based testing libraries for Haskell, JavaScript, Erlang, and C#.
It does not recognise Python Hypothesis, which the parser tests already use.
Getting a score would mean adding Atheris fuzz targets and a ClusterFuzzLite workflow.
For two small, well-covered parsers in a tool that makes no network requests, that is not a good trade.
Left at 0.

## Ceiling

Once the fixable items land (Security-Policy, Signed-Releases, Packaging) and the repository passes 90 days, the overall score should sit around 8.0 to 8.3.
The residual gap is Code-Review, Contributors, Branch-Protection, and Fuzzing, all of which are either solo-maintainer structural limits or a deliberate non-goal.
About 8.3 is the practical maximum without a second maintainer.

## Accepted limitations

Do not re-open these without a change in project circumstances:

- Code-Review (0): needs non-author approvals.
- Contributors (0): needs two or more contributing organisations.
- Branch-Protection (4): the `bump.yml` bypass caps the check.
- Fuzzing (0): Hypothesis is not detected, and a dedicated fuzzing setup is out of proportion to the risk.
- OpenSSF Best Practices silver and gold: require multiple unassociated contributors.
