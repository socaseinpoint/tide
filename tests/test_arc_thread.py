"""U-thread unit — the thread arc kind (нить): one session's memory home.

A thread is a normal arc on disk (``NN-<slug>/`` + ``arc.md``) tagged
``kind: thread`` — so ``open``/``close``/``passport``/seed reuse the arc
machinery, while the picker can filter to threads only.
"""

from __future__ import annotations

import pytest

from tide import fields, paths
from tide.arc import stream
from tide.canon import rev

from tests.conftest import strip_placeholders


# --- create ----------------------------------------------------------------

def test_new_thread_builds_triad_and_passport(tmp_project):
    entry = stream.new_thread(tmp_project, "morning session")
    assert entry.name == "01-morning-session"
    for sub in ("input", "workspace", "output"):
        assert (entry / sub).is_dir()
    doc = entry / "arc.md"
    assert doc.is_file()
    assert fields.read_field(doc, "status") == "active"
    assert fields.read_field(doc, "kind") == "thread"


def test_new_thread_stamps_canon_rev(tmp_project):
    entry = stream.new_thread(tmp_project, "alpha")
    assert fields.read_field(entry / "arc.md", "canon-rev") == rev.compute(tmp_project)


def test_new_thread_shares_numbering_with_arcs(tmp_project):
    a = stream.new_arc(tmp_project, "work")
    t = stream.new_thread(tmp_project, "session")
    assert a.name == "01-work"
    assert t.name == "02-session"


def test_new_thread_empty_slug_raises(tmp_project):
    with pytest.raises(stream.StreamError):
        stream.new_thread(tmp_project, "   ")


# --- kind classification ---------------------------------------------------

def test_entry_kind_distinguishes_arc_goal_thread(tmp_project):
    arc = stream.new_arc(tmp_project, "a")
    goal = stream.new_goal(tmp_project, "g")
    thread = stream.new_thread(tmp_project, "t")
    assert stream.entry_kind(arc) == stream.KIND_ARC
    assert stream.entry_kind(goal) == stream.KIND_GOAL
    assert stream.entry_kind(thread) == stream.KIND_THREAD


def test_is_thread_true_only_for_threads(tmp_project):
    arc = stream.new_arc(tmp_project, "a")
    thread = stream.new_thread(tmp_project, "t")
    assert stream.is_thread(thread) is True
    assert stream.is_thread(arc) is False


# --- listing (picker surface) ----------------------------------------------

def test_thread_entries_filters_to_open_threads(tmp_project):
    stream.new_arc(tmp_project, "work-one")
    t1 = stream.new_thread(tmp_project, "thread-one")
    stream.new_arc(tmp_project, "work-two")
    t2 = stream.new_thread(tmp_project, "thread-two")
    names = [p.name for p in stream.thread_entries(tmp_project)]
    assert names == [t1.name, t2.name]  # arcs filtered out, numeric order


def test_thread_entries_empty_when_none(tmp_project):
    stream.new_arc(tmp_project, "just-work")
    assert stream.thread_entries(tmp_project) == []


def test_thread_entries_closed_flag(tmp_project):
    t = stream.new_thread(tmp_project, "done-thread")
    # a thread closes through the normal arc machinery (placeholder + output guards)
    strip_placeholders(t / "arc.md")
    (t / "output" / "note.md").write_text("x", encoding="utf-8")
    stream.close(tmp_project, "done-thread")
    assert stream.thread_entries(tmp_project) == []  # not open anymore
    closed = [p.name for p in stream.thread_entries(tmp_project, closed=True)]
    assert any("done-thread" in n for n in closed)


# --- reuse: a thread opens like any arc ------------------------------------

def test_thread_opens_via_arc_open(tmp_project):
    stream.new_thread(tmp_project, "resumable")
    entry = stream.open_arc(tmp_project, "resumable")
    assert "resumable" in entry.name
    assert stream.is_thread(entry)
