"""Encoding, byte order marks, line endings, comparison, and hashing."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FIXTURES

from mdcompose.core import files
from mdcompose.core.exit_codes import AttentionError

BODY = "# Heading\n\nA line of prose.\nAnother line.\n"


def test_reads_utf8_without_a_bom() -> None:
    assert files.read_text(FIXTURES / "plain.lf.md") == BODY


def test_reads_utf8_with_a_bom_identically() -> None:
    assert files.read_text(FIXTURES / "plain.bom.md") == BODY


def test_bom_never_appears_in_content() -> None:
    assert files.BOM not in files.read_text(FIXTURES / "plain.bom.md")


def test_crlf_line_endings_survive_reading() -> None:
    assert files.read_text(FIXTURES / "plain.crlf.md") == BODY.replace("\n", "\r\n")


def test_non_utf8_input_is_refused_by_name() -> None:
    with pytest.raises(AttentionError) as raised:
        files.read_text(FIXTURES / "prose.cp1252.md")
    message = str(raised.value)
    assert "prose.cp1252.md" in message
    assert "UTF-8" in message


def test_non_utf8_input_is_never_silently_replaced() -> None:
    with pytest.raises(AttentionError):
        files.read_text(FIXTURES / "prose.cp1252.md")


def test_missing_file_is_reported_by_name(tmp_path: Path) -> None:
    with pytest.raises(AttentionError) as raised:
        files.read_text(tmp_path / "absent.md")
    assert "absent.md" in str(raised.value)


def test_directory_is_not_a_readable_file(tmp_path: Path) -> None:
    with pytest.raises(AttentionError):
        files.read_text(tmp_path)


def test_new_file_is_written_without_a_bom(tmp_path: Path) -> None:
    target = tmp_path / "new.md"
    files.write_text(target, BODY)
    assert not target.read_bytes().startswith(b"\xef\xbb\xbf")


def test_rewriting_a_bom_file_removes_the_bom(tmp_path: Path) -> None:
    target = tmp_path / "had-bom.md"
    target.write_bytes(b"\xef\xbb\xbf" + BODY.encode("utf-8"))
    files.write_text(target, "# Replaced\n")
    assert not target.read_bytes().startswith(b"\xef\xbb\xbf")


def test_new_file_uses_lf(tmp_path: Path) -> None:
    target = tmp_path / "new.md"
    files.write_text(
        target, BODY,
        line_ending=files.line_ending_for(target),
    )
    assert b"\r\n" not in target.read_bytes()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (BODY, files.LF),
        (BODY.replace("\n", "\r\n"), files.CRLF),
        ("a\r\nb\r\nc\r\nd\n", files.CRLF),
        ("a\r\nb\r\nc\nd\n", files.LF),
        ("a\r\nb\nc\nd\n", files.LF),
        ("", files.LF),
    ],
)
def test_dominant_line_ending_wins(text: str, expected: str) -> None:
    """The more frequent convention wins, and an exact tie resolves to LF."""
    assert files.detect_line_ending(text) == expected


def test_rewriting_preserves_crlf(tmp_path: Path) -> None:
    target = tmp_path / "kept.md"
    target.write_bytes(BODY.replace("\n", "\r\n").encode("utf-8"))
    files.write_text(
        target, "# Replaced\nSecond line.\n",
        line_ending=files.line_ending_for(target),
    )
    raw = target.read_bytes()
    assert b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")


def test_rewriting_preserves_lf(tmp_path: Path) -> None:
    target = tmp_path / "kept.md"
    target.write_bytes(BODY.encode("utf-8"))
    files.write_text(
        target, "# Replaced\nSecond line.\n",
        line_ending=files.line_ending_for(target),
    )
    assert b"\r\n" not in target.read_bytes()


def test_bom_only_difference_compares_equal() -> None:
    assert files.content_equal(files.BOM + BODY, BODY)


def test_line_ending_only_difference_compares_equal() -> None:
    assert files.content_equal(BODY, BODY.replace("\n", "\r\n"))


def test_lone_carriage_returns_normalize_too() -> None:
    assert files.content_equal("a\rb\rc", "a\nb\nc")


def test_trailing_blank_line_is_a_real_difference() -> None:
    assert not files.content_equal(BODY, BODY + "\n")


def test_hash_is_stable_across_line_endings() -> None:
    assert files.hash_content(BODY) == files.hash_content(BODY.replace("\n", "\r\n"))


def test_hash_is_stable_across_a_bom() -> None:
    assert files.hash_content(BODY) == files.hash_content(files.BOM + BODY)


def test_hash_is_stable_across_the_committed_fixtures() -> None:
    """A CRLF checkout and an LF checkout of one file must agree.

    This is what allows a manifest carrying hashes to be committed.
    """
    lf = files.hash_content(files.read_text(FIXTURES / "plain.lf.md"))
    crlf = files.hash_content(files.read_text(FIXTURES / "plain.crlf.md"))
    bom = files.hash_content(files.read_text(FIXTURES / "plain.bom.md"))
    assert lf == crlf == bom


def test_hash_changes_when_one_character_changes() -> None:
    assert files.hash_content(BODY) != files.hash_content(BODY.replace("prose", "prosa"))


def test_no_op_write_is_detected(tmp_path: Path) -> None:
    target = tmp_path / "same.md"
    assert files.write_if_changed(target, BODY) is True
    assert files.write_if_changed(target, BODY) is False


def test_no_op_write_is_detected_across_line_endings(tmp_path: Path) -> None:
    target = tmp_path / "crlf.md"
    target.write_bytes(BODY.replace("\n", "\r\n").encode("utf-8"))
    assert files.write_if_changed(target, BODY) is False
    assert b"\r\n" in target.read_bytes()


def test_changed_content_is_written_in_the_existing_convention(tmp_path: Path) -> None:
    target = tmp_path / "crlf.md"
    target.write_bytes(BODY.replace("\n", "\r\n").encode("utf-8"))
    assert files.write_if_changed(target, "# Different\nText.\n") is True
    assert b"\r\n" in target.read_bytes()


# --- hardening: read size cap ---


def test_a_file_over_the_read_limit_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "huge.md"
    target.write_bytes(b"x" * (files.MAX_READ_BYTES + 1))
    with pytest.raises(AttentionError, match="limit"):
        files.read_text(target)


def test_a_file_at_the_read_limit_is_allowed(tmp_path: Path) -> None:
    target = tmp_path / "big.md"
    target.write_bytes(b"x" * files.MAX_READ_BYTES)
    assert len(files.read_text(target)) == files.MAX_READ_BYTES


# --- hardening: writes are atomic and do not follow a symlink ---


def test_a_failed_write_leaves_the_previous_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "keep.md"
    target.write_text("original\n", encoding="utf-8")

    def boom(self: Path, _other: Path) -> None:
        raise OSError(13, "denied")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(AttentionError):
        files.write_text(target, "replacement\n")
    assert target.read_text(encoding="utf-8") == "original\n"
    assert list(tmp_path.iterdir()) == [target]  # scratch file cleaned up


def test_a_write_replaces_a_symlink_rather_than_following_it(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("must not change\n", encoding="utf-8")
    link = tmp_path / "AGENTS.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation not permitted here")

    files.write_text(link, "composed\n")
    assert outside.read_text(encoding="utf-8") == "must not change\n"
    assert not link.is_symlink()
    assert link.read_text(encoding="utf-8") == "composed\n"
