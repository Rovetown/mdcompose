"""Prompt helpers: every prompt refuses to guess and names the flag that answers it."""

from __future__ import annotations

import pytest
from conftest import make_output

from mdcompose import prompts
from mdcompose.core.exit_codes import AttentionError

# 4.12 non-interactive with no flag: the missing answer is an error naming the flag


def test_confirm_without_a_terminal_refuses_and_names_the_flag() -> None:
    out = make_output()
    with pytest.raises(AttentionError, match="--yes"):
        prompts.confirm(out.context, "delete it?", flag="--yes")


def test_prompt_choice_without_a_terminal_refuses_and_names_the_flag() -> None:
    out = make_output()
    with pytest.raises(AttentionError, match="--mode") as caught:
        prompts.prompt_choice(
            out.context, "the mode", options=("import", "copy"), default="import", flag="--mode"
        )
    assert "import, copy" in caught.value.message


# 4.8 JSON mode refuses to prompt even when a terminal is attached


def test_confirm_in_json_mode_refuses_and_names_the_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prompts, "is_interactive", lambda: True)
    out = make_output(json_mode=True)
    with pytest.raises(AttentionError, match="--yes"):
        prompts.confirm(out.context, "overwrite?", flag="--yes")


def test_prompt_choice_in_json_mode_refuses_and_names_the_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prompts, "is_interactive", lambda: True)
    out = make_output(json_mode=True)
    with pytest.raises(AttentionError, match="--on-drift"):
        prompts.prompt_choice(
            out.context,
            "drift",
            options=("keep", "overwrite", "abort"),
            default="keep",
            flag="--on-drift",
        )


# the flag path: an answer supplied up front skips the question entirely


def test_confirm_returns_true_when_the_answer_was_supplied() -> None:
    out = make_output()
    assert prompts.confirm(out.context, "proceed?", assume_yes=True, flag="--yes") is True


# 4.2 declining an optional prompt is a valid outcome, not an error


def test_declining_a_confirm_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompts, "is_interactive", lambda: True)
    monkeypatch.setattr("typer.confirm", lambda *_a, **_k: False)
    out = make_output()
    assert prompts.confirm(out.context, "delete it?", flag="--yes") is False
