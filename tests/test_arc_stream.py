"""U3 unit — arc-stream lifecycle: create / open / close / reopen / supersede."""

from __future__ import annotations

import pytest

from tide import fields, paths
from tide.arc import stream
from tide.cannon import rev


# --- create ----------------------------------------------------------------

def test_new_arc_builds_triad_and_passport(tmp_project):
    entry = stream.new_arc(tmp_project, "fix the leak")
    assert entry.name == "01-fix-the-leak"
    for sub in ("input", "workspace", "output"):
        assert (entry / sub).is_dir()
    doc = entry / "arc.md"
    assert doc.is_file()
    assert fields.read_field(doc, "status") == "active"


def test_new_arc_stamps_cannon_rev(tmp_project):
    entry = stream.new_arc(tmp_project, "alpha")
    stamped = fields.read_field(entry / "arc.md", "cannon-rev")
    assert stamped == rev.compute(tmp_project)
    assert stamped  # non-empty


def test_new_arc_numbering_is_continuous(tmp_project):
    a = stream.new_arc(tmp_project, "one")
    b = stream.new_arc(tmp_project, "two")
    assert a.name == "01-one"
    assert b.name == "02-two"


def test_new_arc_empty_slug_raises(tmp_project):
    with pytest.raises(stream.StreamError):
        stream.new_arc(tmp_project, "!!!")


def test_new_goal_builds_substream_and_doc(tmp_project):
    goal = stream.new_goal(tmp_project, "ship v1")
    assert goal.name == "01-@ship-v1"
    assert (goal / "arcs").is_dir()
    doc = goal / "ship-v1-goal.md"
    assert doc.is_file()
    assert fields.read_field(doc, "status") == "active"


def test_arc_and_goal_share_one_counter(tmp_project):
    stream.new_arc(tmp_project, "a")          # 01
    goal = stream.new_goal(tmp_project, "g")  # 02 (not 01)
    assert goal.name == "02-@g"


# --- goal substream --------------------------------------------------------

def test_new_arc_nests_under_open_goal(tmp_project):
    stream.new_goal(tmp_project, "ship")
    sub = stream.new_arc(tmp_project, "wire-api", goal_slug="ship")
    assert sub.parent.name == "arcs"
    assert sub.parent.parent.name == "01-@ship"
    assert sub.name == "01-wire-api"  # local substream numbering


def test_new_arc_under_missing_goal_raises(tmp_project):
    with pytest.raises(stream.StreamError):
        stream.new_arc(tmp_project, "x", goal_slug="nope")


def test_new_arc_under_closed_goal_raises(tmp_project):
    goal = stream.new_goal(tmp_project, "ship")
    (goal / "output" / "done.md").write_text("x", encoding="utf-8")
    stream.close(tmp_project, "ship")
    with pytest.raises(stream.StreamError):
        stream.new_arc(tmp_project, "late", goal_slug="ship")


# --- open / resume ---------------------------------------------------------

def test_open_restamps_cannon_rev_after_cannon_moves(tmp_project):
    entry = stream.new_arc(tmp_project, "alpha")
    old_rev = fields.read_field(entry / "arc.md", "cannon-rev")
    # move the cannon → rev changes
    canon = paths.canon_file(tmp_project)
    canon.write_text(canon.read_text(encoding="utf-8") + "\nmoved\n", encoding="utf-8")
    new_rev = stream.open_arc(tmp_project, "alpha")
    assert rev.compute(tmp_project) != old_rev
    stamped = fields.read_field((tmp_project / ".tide/arcs/01-alpha") / "arc.md", "cannon-rev")
    assert stamped == rev.compute(tmp_project)


def test_open_missing_arc_raises(tmp_project):
    with pytest.raises(stream.StreamError):
        stream.open_arc(tmp_project, "ghost")


# --- close (guard + dual-mark) ---------------------------------------------

def test_close_refuses_empty_output(tmp_project):
    stream.new_arc(tmp_project, "alpha")
    with pytest.raises(stream.StreamError):
        stream.close(tmp_project, "alpha")


def test_close_dual_marks_done(tmp_project):
    entry = stream.new_arc(tmp_project, "alpha")
    (entry / "output" / "result.md").write_text("done", encoding="utf-8")
    closed = stream.close(tmp_project, "alpha")
    assert closed.name == "__01-alpha__"
    assert closed.is_dir()
    assert not entry.exists()
    assert fields.read_field(closed / "arc.md", "status") == "done"


def test_close_force_overrides_empty_output(tmp_project):
    stream.new_arc(tmp_project, "alpha")
    closed = stream.close(tmp_project, "alpha", force=True)
    assert closed.name == "__01-alpha__"
    assert fields.read_field(closed / "arc.md", "status") == "done"


def test_close_prefers_goal_over_arc_same_slug(tmp_project):
    # an arc AND a goal both named 'ship' → close must hit the goal
    stream.new_arc(tmp_project, "ship")    # 01-ship
    goal = stream.new_goal(tmp_project, "ship")  # 02-@ship
    (goal / "output" / "x.md").write_text("x", encoding="utf-8")
    closed = stream.close(tmp_project, "ship")
    assert closed.name == "__02-@ship__"
    assert (tmp_project / ".tide/arcs/01-ship").is_dir()  # the plain arc untouched


def test_close_then_new_never_reuses_number(tmp_project):
    entry = stream.new_arc(tmp_project, "alpha")
    (entry / "output" / "r.md").write_text("x", encoding="utf-8")
    stream.close(tmp_project, "alpha")
    nxt = stream.new_arc(tmp_project, "beta")
    assert nxt.name == "02-beta"  # 01 consumed by the closed arc


# --- reopen ----------------------------------------------------------------

def test_reopen_reverses_close(tmp_project):
    entry = stream.new_arc(tmp_project, "alpha")
    (entry / "output" / "r.md").write_text("x", encoding="utf-8")
    stream.close(tmp_project, "alpha")
    opened = stream.reopen(tmp_project, "alpha")
    assert opened.name == "01-alpha"
    assert not (tmp_project / ".tide/arcs/__01-alpha__").exists()
    assert fields.read_field(opened / "arc.md", "status") == "active"


def test_reopen_prefers_goal_over_arc(tmp_project):
    stream.new_arc(tmp_project, "ship")
    goal = stream.new_goal(tmp_project, "ship")
    (goal / "output" / "x.md").write_text("x", encoding="utf-8")
    stream.close(tmp_project, "ship")  # closes the goal
    opened = stream.reopen(tmp_project, "ship")
    assert opened.name == "02-@ship"


# --- supersede -------------------------------------------------------------

def test_supersede_arc_links_old_new_and_seeds_from(tmp_project):
    stream.new_arc(tmp_project, "old-plan")
    entry = stream.supersede(tmp_project, "old-plan", "new-plan")
    # old closed (no output guard needed), new created same kind
    assert (tmp_project / ".tide/arcs/__01-old-plan__").is_dir()
    assert entry.name == "02-new-plan"
    doc = entry / "arc.md"
    assert fields.read_field(doc, "supersedes") == "old-plan"
    # supersedes sits right after status:
    lines = doc.read_text(encoding="utf-8").splitlines()
    si = next(i for i, ln in enumerate(lines) if ln.startswith("status:"))
    assert lines[si + 1] == "supersedes: old-plan"
    # from-seed written into input/
    seed = entry / "input" / "from-old-plan.md"
    assert seed.is_file()
    assert "supersedes old-plan" in seed.read_text(encoding="utf-8")


def test_supersede_reads_via_prev_alias(tmp_project):
    stream.new_arc(tmp_project, "old")
    entry = stream.supersede(tmp_project, "old", "new")
    # written as supersedes:, readable through the prev: alias
    assert fields.read_field(entry / "arc.md", "prev") == "old"


def test_supersede_preserves_goal_kind(tmp_project):
    stream.new_goal(tmp_project, "old-goal")
    entry = stream.supersede(tmp_project, "old-goal", "new-goal")
    assert entry.name == "02-@new-goal"
    doc = entry / "new-goal-goal.md"
    assert doc.is_file()
    assert fields.read_field(doc, "supersedes") == "old-goal"
    assert "This goal supersedes old-goal" in (entry / "input" / "from-old-goal.md").read_text(encoding="utf-8")


def test_supersede_tolerates_wrapped_old_ref(tmp_project):
    stream.new_arc(tmp_project, "old")
    entry = stream.supersede(tmp_project, "__old__", "new")
    assert (tmp_project / ".tide/arcs/__01-old__").is_dir()
    assert fields.read_field(entry / "arc.md", "supersedes") == "old"
