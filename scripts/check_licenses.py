"""Fail if any installed distribution carries a license outside the allowlist.

Runs against whatever is installed in the current environment, so the caller
decides the scope:

    uv sync --no-dev && uv run python scripts/check_licenses.py   # runtime only
    uv sync          && uv run python scripts/check_licenses.py --report

Runtime licenses are what constrains the license this project can ship under, so
an unexpected one there is an error. Development-only tool licenses do not
propagate to a user who installs the package, so ``--report`` prints them
without failing.
"""

from __future__ import annotations

import argparse
import sys
from importlib import metadata

# License policy for a dependency, by tier. License compatibility flows inward:
# a dependency's license restricts what mdcompose itself may be licensed as only
# if that dependency is copyleft. Every license below is permissive, so any of
# them may appear in the tree without constraining mdcompose's own license.
#
#   ALLOW       permissive: attribution or a NOTICE file at most. Apache-2.0
#               also carries a patent grant, still fine for an MIT project.
#   CASE BY CASE  weak, file-level copyleft (MPL-2.0). Depending on an
#               unmodified package under it and shipping alongside is fine;
#               only that file cannot be relicensed. Not auto-allowed: add the
#               specific package to KNOWN after checking it.
#   DENY        strong or linking copyleft (GPL, LGPL, AGPL, EUPL, SSPL) and
#               anything unrecognized. These would force mdcompose copyleft, or
#               need a human to classify. The check fails on all of them.
#
# SPDX identifiers plus the noisier free-text spellings the ecosystem still
# emits. Anything not here fails, which is the safe default.
ALLOWED = {
    "0bsd",
    "apache-2.0",
    "apache-2.0 or bsd-2-clause",
    "apache license 2.0",
    "apache software license",
    "bsd",
    "bsd license",
    "bsd-2-clause",
    "bsd-2-clause license",
    "bsd-3-clause",
    "bsd-3-clause license",
    "isc",
    "isc license",
    "isc license (iscl)",
    "mit",
    "mit license",
    "mit no attribution",
    "mit-0",
    "psf-2.0",
    "python software foundation license",
    "the unlicense",
    "unlicense",
    "zlib",
}

# Weak copyleft: allowed only for a package that has been looked at and added to
# KNOWN with the exact license. Not put in ALLOWED, so a new MPL dependency
# fails the check until someone confirms it is unmodified and shipped alongside.
CASE_BY_CASE = {"mpl-2.0", "mozilla public license 2.0 (mpl 2.0)"}

# Distributions whose own license text lives elsewhere or is trivially known;
# keeps the check from failing on a metadata gap in a package we have eyeballed.
KNOWN = {
    "colorama": "BSD-3-Clause",
    "markdown-it-py": "MIT",
    "mdurl": "MIT",
    "prompt-toolkit": "BSD-3-Clause",
    "wcwidth": "MIT",
}


def _license_of(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    classifiers = [
        value.split("::")[-1].strip()
        for value in meta.get_all("Classifier", [])
        if value.startswith("License ::")
    ]
    if classifiers:
        return "; ".join(classifiers)
    declared = (meta.get("License") or "").strip()
    if declared and "\n" not in declared and len(declared) < 60:
        return declared
    return KNOWN.get(_canonical(meta["Name"]), "UNKNOWN")


def _canonical(name: str) -> str:
    return name.lower().replace("_", "-")


def _is_allowed(license_text: str) -> bool:
    parts = [
        piece.strip().lower()
        for piece in license_text.replace(" AND ", "/").replace(" OR ", "/").split("/")
        if piece.strip()
    ]
    return bool(parts) and all(part in ALLOWED for part in parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print every distribution and its license without failing.",
    )
    args = parser.parse_args()

    rows = sorted(
        (dist.metadata["Name"], _license_of(dist))
        for dist in metadata.distributions()
        if dist.metadata["Name"] and _canonical(dist.metadata["Name"]) != "mdcompose"
    )

    width = max((len(name) for name, _ in rows), default=0)
    problems: list[str] = []
    for name, license_text in rows:
        ok = _is_allowed(license_text)
        mark = "ok " if ok else "!! "
        print(f"{mark}{name.ljust(width)}  {license_text}")
        if not ok:
            problems.append(f"{name}: {license_text}")

    if problems and not args.report:
        print()
        print("licenses outside the allowlist:")
        for line in problems:
            print("  " + line)
        weak = [p for p in problems if any(c in p.lower() for c in CASE_BY_CASE)]
        if weak:
            print(
                "One is weak copyleft (MPL-2.0). If the package is unmodified and shipped "
                "alongside, add it to KNOWN with its exact license after checking it."
            )
        print("If one is genuinely permissive, add its SPDX id to ALLOWED.")
        return 1
    print()
    print(f"{len(rows)} distributions checked, {len(problems)} outside the allowlist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
