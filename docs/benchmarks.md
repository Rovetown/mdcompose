# Benchmark baseline

The suite lives in `tests/benchmarks/` and is excluded from the normal test run.
Run it with:

    uv run --group benchmark pytest tests/benchmarks

Each case exercises one core operation on a large or many-file input: a 200 KB
markdown document for the section parser, a CLAUDE.md whose managed block holds
200 KB, a 300-snippet library, and a project whose AGENTS.md and CLAUDE.md both
carry large managed blocks.

## What the numbers are for

Wall-clock timing on a shared runner has too much variance to gate a merge on.
The plan is for CodSpeed to run this same suite instrumented once the GitHub
repo exists (`benchmarks` job in `ci.yml`, currently dormant): it measures
instruction counts rather than seconds, so a regression shows up as a real
delta on a pull request instead of noise. Until then this file is the baseline,
recorded by hand, and a local run is compared against it by eye.

## Baseline

Recorded 2026-09-10, Windows 11, Python 3.11.14, `pytest-benchmark` 5.3.0.
Median of the timed rounds:

| Operation | Input | Median |
| --- | --- | --- |
| `sections.extract` | ~12 sections picked from a 200 KB file | 0.04 ms |
| `managed_block.upsert` | replace a 200 KB managed block | 1.6 ms |
| `sections.parse_sections` | 200 KB markdown, ~1800 sections | 3.9 ms |
| `manifest.detect_drift` | two files with 200 KB managed blocks | 4.0 ms |
| `report.build_doctor_report` | same project | 4.3 ms |
| `composition.apply_to_file` | write a block into a 200 KB CLAUDE.md | 10.7 ms |
| `eject.plan_eject` | same project | 7.8 ms |
| `snippets.view` | 300-snippet library | 67 ms |

## Reading it

Nothing here is slow enough to act on today; a full `doctor` or `init` on a
realistic project stays under about 15 ms of core work. The library load is the
one line worth watching: it is linear in the snippet count at roughly 0.22 ms
per file, almost all of it YAML frontmatter parsing, so a library in the
thousands would start to be felt.

## The performance item: nothing to do yet

The roadmap suggested three optimisations. Measured against this suite, none is
justified:

- **Caching `PlatformInfo`.** Each command calls `detect_platform` once;
  `build_doctor_report` at 4.3 ms is dominated by hashing the 200 KB blocks, not
  by detection.
- **Reading a file once and passing the text down.** The write paths do re-read
  a file to detect its line ending after the caller already read it, but
  reverting that read off `composition.apply_to_file` moved the median from
  10.7 ms to 10.6 ms, inside the noise: the read is cheap next to normalising
  and writing 200 KB.
- **Skipping a re-parse when the hash is unchanged.** `detect_drift` is 4.0 ms
  and already hashes rather than re-parsing; there is no re-parse to skip.

Revisit if a real workload, most likely a library in the thousands, shows a
cost this suite does not.
