"""Wall-clock baselines for the operations that touch large or many files.

Run locally with `uv run --group benchmark pytest tests/benchmarks`; the
`benchmarks` job in ci.yml runs the same suite under CodSpeed so the numbers are
stable across runners. These assert only that the operation still produces a
sane result: the timing is the point, and a regression is judged against the
recorded baseline rather than a hard threshold.
"""

from __future__ import annotations

from pathlib import Path

from mdcompose.core import composition, managed_block, sections
from mdcompose.core import eject as eject_module
from mdcompose.core import manifest as manifest_module
from mdcompose.core import report as report_module
from mdcompose.core import snippets as snippets_module
from mdcompose.core.platform import PlatformInfo

CLAUDE_BLOCK = managed_block.CLAUDE_MANAGED_BLOCK


def test_parse_sections_on_a_200kb_file(benchmark, large_markdown: str) -> None:
    result = benchmark(lambda: sections.parse_sections(large_markdown, source_name="big.md"))
    assert len(result) > 100


def test_extract_a_selection_from_a_200kb_file(benchmark, large_markdown: str) -> None:
    parsed = sections.parse_sections(large_markdown, source_name="big.md")
    picked = tuple(parsed[index] for index in range(0, len(parsed), max(1, len(parsed) // 12)))
    result = benchmark(lambda: sections.extract(picked))
    assert result


def test_load_a_library_of_300_snippets(benchmark, library_dir: Path) -> None:
    result = benchmark(lambda: snippets_module.view(library_dir))
    assert len(result.snippets) == 300


def test_upsert_into_a_large_claude_md(benchmark, large_claude_md: str) -> None:
    replacement = "New composed content.\n"
    result = benchmark(
        lambda: managed_block.upsert(
            large_claude_md, CLAUDE_BLOCK, replacement, Path("CLAUDE.md")
        )
    )
    assert replacement in result


def test_write_a_block_into_a_large_claude_md(benchmark, drifted_project: Path) -> None:
    target = drifted_project / "CLAUDE.md"
    pristine = target.read_bytes()
    body = "".join(f"## Fresh {index}\n\nreplacement line for {index}\n\n" for index in range(4000))

    def reset() -> None:
        target.write_bytes(pristine)

    def write() -> bool:
        return composition.apply_to_file(target, CLAUDE_BLOCK, body)

    benchmark.pedantic(write, setup=reset, rounds=30, iterations=1)


def test_detect_drift_on_large_managed_files(benchmark, drifted_project: Path) -> None:
    manifest = manifest_module.load_manifest(manifest_module.manifest_path(drifted_project))
    assert manifest is not None
    result = benchmark(lambda: manifest_module.detect_drift(manifest, drifted_project))
    assert len(result) == 2


def test_build_doctor_report_on_large_managed_files(benchmark, drifted_project: Path) -> None:
    info = PlatformInfo(os_name="linux", is_wsl=False)
    result = benchmark(
        lambda: report_module.build_doctor_report(
            project_root=drifted_project,
            info=info,
            environ={},
            config_directory=drifted_project / "config",
        )
    )
    assert result.drift is not None


def test_plan_eject_on_large_managed_files(benchmark, drifted_project: Path) -> None:
    result = benchmark(lambda: eject_module.plan_eject(drifted_project, strip=False))
    assert result.changes
