"""U6 unit — contract.ask: durable per-arc asks, ask/answer, own NN numbering."""

from __future__ import annotations

import pytest

from tide import fields
from tide.arc import stream
from tide.contract import ask, model


def _arc(root, slug="fix-leak"):
    return stream.new_arc(root, slug)


def test_ask_creates_open_question(tmp_project):
    _arc(tmp_project)
    path = ask.ask(tmp_project, "fix-leak", "valve-type", question="which valve?", from_ref="worker-3")
    assert path.name == "01-valve-type.md"
    text = path.read_text(encoding="utf-8")
    assert "from: worker-3" in text
    assert "state: open" in text
    assert "## question" in text
    assert "which valve?" in text
    assert "## answer" in text


def test_ask_uses_own_per_arc_numbering(tmp_project):
    _arc(tmp_project)
    ask.ask(tmp_project, "fix-leak", "first")
    second = ask.ask(tmp_project, "fix-leak", "second")
    assert second.name == "02-second.md"


def test_answer_fills_answer_and_flips_state(tmp_project):
    _arc(tmp_project)
    ask.ask(tmp_project, "fix-leak", "valve-type", question="which valve?")
    path = ask.answer(tmp_project, "fix-leak", "valve-type", answer="the brass one")
    assert fields.read_field(path, "state") == "answered"
    text = path.read_text(encoding="utf-8")
    assert "the brass one" in text
    # question preserved
    assert "which valve?" in text


def test_answer_resolves_by_number(tmp_project):
    _arc(tmp_project)
    ask.ask(tmp_project, "fix-leak", "valve-type", question="q")
    path = ask.answer(tmp_project, "fix-leak", "01", answer="a")
    assert fields.read_field(path, "state") == "answered"


def test_answer_no_match_raises(tmp_project):
    _arc(tmp_project)
    ask.ask(tmp_project, "fix-leak", "valve-type")
    with pytest.raises(model.ContractError):
        ask.answer(tmp_project, "fix-leak", "nope", answer="x")


def test_list_asks_reports_state(tmp_project):
    _arc(tmp_project)
    ask.ask(tmp_project, "fix-leak", "one", question="q1")
    ask.ask(tmp_project, "fix-leak", "two", question="q2")
    ask.answer(tmp_project, "fix-leak", "one", answer="a1")
    items = ask.list_asks(tmp_project, "fix-leak")
    assert [i["slug"] for i in items] == ["one", "two"]
    assert items[0]["state"] == "answered"
    assert items[1]["state"] == "open"
