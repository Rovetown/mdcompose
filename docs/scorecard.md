# OpenSSF Scorecard

Where the project stands on the OpenSSF Scorecard, and what is worth doing about it.
The action items live in [TODO.md](../TODO.md), in the `Next` section, sequenced with the rest of the release work.
This file is the reasoning behind them.

Live score: <https://scorecard.dev/viewer/?uri=github.com/Rovetown/mdcompose> Raw JSON: <https://api.scorecard.dev/projects/github.com/Rovetown/mdcompose>

Last reviewed: 2026-09-11, commit `b730e9e` (the `scorecard.yml` run this commit
triggered), overall score 7.2.

## Checks already at 10

Pinned-Dependencies, Token-Permissions, SAST, CI-Tests, License, Vulnerabilities, Binary-Artifacts, Dangerous-Workflow, Dependency-Update-Tool, Security-Policy, Signed-Releases, Packaging.
These need nothing.
Do not regress them.

## Gap table

| Check | Score | Verdict | Reason |
| ----- | ----- | ------- | ------ |
| Maintained | 0 | Ignore, time heals it | Age penalty only: the repository is under 90 days old. Clears once it passes 90 days with regular commit or issue activity. |
| CII-Best-Practices | 0 | Medium priority | No OpenSSF Best Practices registration. A passing badge is worth 5 on this check. |
| Branch-Protection | 4 | Capped, accept | Scorecard treats `EnforceAdmins` as false whenever any ruleset bypass actor exists, and `bump.yml` needs the maintainer bypass. |
| Code-Review | 0 | Cannot fix | Needs approving reviews from someone other than the commit author. Single maintainer. |
| Contributors | 0 | Cannot fix | Needs contributors affiliated with two or more organisations. Single maintainer. |
| Fuzzing | 0 | Low value, skip | Scorecard does not detect Python Hypothesis. A libFuzzer or Atheris plus ClusterFuzzLite setup is disproportionate for a Markdown CLI with two small parsers. |

## Detail

### Security-Policy (done, 10)

Scorecard scores the policy in three parts: 6 points for a contactable link (an `https://` URL or an email address), 3 points for free-form explanatory text, 1 point for specific vulnerability and disclosure language.
Fixed by adding a line to [SECURITY.md](../SECURITY.md) pointing at `https://github.com/Rovetown/mdcompose/security/advisories/new`, the private advisory form -- the same channel the prose already described, now in a form the check can see.

### Signed-Releases (done, 10)

The check looks at the assets attached to the last several GitHub Releases for a signature file (`*.sig`, `*.asc`, `*.sigstore.json`, and similar) or a SLSA provenance file (`*.intoto.jsonl`, worth the full 10).
The PEP 740 attestations that `pypa/gh-action-pypi-publish` generates go to PyPI, not to the GitHub Release, so they do not count here.

`release.yml` runs `actions/attest-build-provenance` and attaches `mdcompose.intoto.jsonl` to the `gh release create` asset list, with `id-token: write` and `attestations: write` on the `github-release` job alongside `contents: write`.
Confirmed in the `scorecard.yml` run for commit `b730e9e`: `"1 out of the last 1 releases have a total of 1 signed artifacts"`, citing `mdcompose.intoto.jsonl` on the `v0.1.0` release.

### Packaging (done, 10)

Nothing was needed. `release.yml` publishes through `pypa/gh-action-pypi-publish`, which is on Scorecard's detection list, and the check flipped to 10 as soon as the first release ran.

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

Security-Policy, Signed-Releases, and Packaging are done; the score sits at 7.2.
Once CII-Best-Practices passes and the repository clears 90 days (Maintained), it should land around 8.0 to 8.3.
The residual gap is Code-Review, Contributors, Branch-Protection, and Fuzzing, all of which are either solo-maintainer structural limits or a deliberate non-goal.
About 8.3 is the practical maximum without a second maintainer.

Note for anyone reading the public badge: it can lag the repository's own `scorecard.yml` run by up to a few days, since `img.shields.io/ossf-scorecard` reads from the OpenSSF API's own re-scan schedule, not from this repository's Actions run directly.
The run itself (`gh run view <id> --log`, or the Security tab's code scanning alerts) is the current source of truth.

## Accepted limitations

Do not re-open these without a change in project circumstances:

- Code-Review (0): needs non-author approvals.
- Contributors (0): needs two or more contributing organisations.
- Branch-Protection (4): the `bump.yml` bypass caps the check.
- Fuzzing (0): Hypothesis is not detected, and a dedicated fuzzing setup is out of proportion to the risk.
- OpenSSF Best Practices silver and gold: require multiple unassociated contributors.
