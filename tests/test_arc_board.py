"""U8 unit — the STREAM board renderer (computed N/M + CANDIDATES + drift/unmerged)."""

from __future__ import annotations

from tide import fields, paths
from tide.arc import board, candidate, stream


def _set_goal(passport_path, text):
    fields.set_field(passport_path, "goal", text)


# --- goal badge (computed N/M, never hand-ticked) --------------------------

def test_goal_badge_counts_closed_over_total(tmp_project):
    stream.new_goal(tmp_project, "ship")
    stream.new_arc(tmp_project, "wire", goal_slug="ship")   # 01-wire (open)
    stream.new_arc(tmp_project, "test", goal_slug="ship")   # 02-test (open)
    stream.close(tmp_project, "wire", goal_slug="ship", force=True)
    goal_dir = paths.arcs_dir(tmp_project) / "01-@ship"
    assert board.goal_badge(goal_dir) == (1, 2)


def test_goal_badge_none_for_zero_subarcs(tmp_project):
    # empty badge for a zero-sub-arc goal — never 0/0
    goal_dir = stream.new_goal(tmp_project, "fresh")
    assert board.goal_badge(goal_dir) is None


def test_zero_subarc_goal_has_no_badge_suffix(tmp_project):
    stream.new_goal(tmp_project, "fresh")
    out = board.render_board(tmp_project)
    line = next(ln for ln in out.splitlines() if "01-@fresh" in ln)
    assert "/" not in line  # no N/M badge rendered


# --- full STREAM snapshot --------------------------------------------------

def test_render_board_full_snapshot(tmp_project):
    a = stream.new_arc(tmp_project, "alpha")
    _set_goal(a / "arc.md", "fix the leak")

    g = stream.new_goal(tmp_project, "ship")
    _set_goal(g / "ship-goal.md", "ship it")

    sub1 = stream.new_arc(tmp_project, "wire", goal_slug="ship")
    _set_goal(sub1 / "arc.md", "wiring")
    sub2 = stream.new_arc(tmp_project, "test", goal_slug="ship")
    _set_goal(sub2 / "arc.md", "testing")
    stream.close(tmp_project, "wire", goal_slug="ship", force=True)

    candidate.new_candidate(tmp_project, "idea", from_arc="alpha", body="an idea")

    expected = (
        "STREAM\n"
        "  01-alpha  [active]  fix the leak\n"
        "  02-@ship  [active]  ship it  (1/2 ✓)\n"
        "    ✓ __01-wire__  wiring\n"
        "    ○ 02-test  [active]  testing\n"
        "\n"
        "CANDIDATES\n"
        "  01-idea  from alpha"
    )
    assert board.render_board(tmp_project) == expected


def test_render_board_empty_stream(tmp_project):
    assert board.render_board(tmp_project) == "STREAM\n  (empty stream)"


# --- drift flag (tide net-new) ---------------------------------------------

def test_open_arc_flags_drift_when_cannon_moves(tmp_project):
    a = stream.new_arc(tmp_project, "alpha")
    _set_goal(a / "arc.md", "do it")
    # move the cannon under the arc WITHOUT restamping (no open_arc) → drift
    canon = paths.canon_file(tmp_project)
    canon.write_text(canon.read_text(encoding="utf-8") + "\nmoved\n", encoding="utf-8")
    out = board.render_board(tmp_project)
    line = next(ln for ln in out.splitlines() if "01-alpha" in ln)
    assert board.DRIFT_FLAG in line


def test_closed_arc_does_not_flag_drift(tmp_project):
    a = stream.new_arc(tmp_project, "alpha")
    (a / "output" / "r.md").write_text("x", encoding="utf-8")
    stream.close(tmp_project, "alpha")
    canon = paths.canon_file(tmp_project)
    canon.write_text(canon.read_text(encoding="utf-8") + "\nmoved\n", encoding="utf-8")
    out = board.render_board(tmp_project)
    line = next(ln for ln in out.splitlines() if "__01-alpha__" in ln)
    assert board.DRIFT_FLAG not in line


# --- unmerged-delta barrier flag (tide net-new) ----------------------------

def test_unmerged_delta_is_flagged(tmp_project):
    a = stream.new_arc(tmp_project, "leak")
    (a / "output" / "r.md").write_text("x", encoding="utf-8")
    (a / "delta.md").write_text("# delta — leak\nmerged: no\n\npatched the leak\n", encoding="utf-8")
    stream.close(tmp_project, "leak")  # closed dir still carries an unmerged delta
    out = board.render_board(tmp_project)
    assert "UNMERGED DELTAS" in out
    assert "tide cannon merge leak" in out


# --- supersede link --------------------------------------------------------

def test_supersedes_link_shown(tmp_project):
    stream.new_arc(tmp_project, "old")
    stream.supersede(tmp_project, "old", "new")
    out = board.render_board(tmp_project)
    line = next(ln for ln in out.splitlines() if " 02-new" in ln)
    assert "(supersedes old)" in line
