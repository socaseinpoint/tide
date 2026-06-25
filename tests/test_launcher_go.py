"""go — ``tide go``: the light ENTRY dispatcher (symmetric mirror of handoff).

``tide go`` routes the human back INTO tide with one light question — resume a
prior thread, or start new — then delegates the launch to ``tide terminal`` (the
single scoped+skip-perms path). These tests pin the resume classification (the
core logic: ``continue`` shows + seeds from the distil, ``close`` is hidden, no
handoff is ``raw`` from the passport), the menu rendering, and the dry-run wiring
(menus print, terminal launch is built but never exec'd).
"""

from __future__ import annotations

from pathlib import Path

from tide.launcher import go


# --- fixtures: build open arcs with/without handoffs in a control-home ------

def _make_arc(root: Path, name: str, *, goal: str = "do the thing") -> Path:
    """Create an open ``NN-slug`` arc dir with a minimal passport; return its dir."""
    arc = root / ".tide" / "arcs" / name
    arc.mkdir(parents=True, exist_ok=True)
    (arc / "arc.md").write_text(
        "# {0}\n\ngoal: {1}\nstatus: active\n".format(name, goal), encoding="utf-8"
    )
    return arc


def _write_handoff(arc: Path, *, date: str, mode: str, where: str = "") -> Path:
    """Drop a ``workspace/handoff-<date>.md`` distil with the given mode/where."""
    ws = arc / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    body = (
        "# tide handoff — x\n\nmode: {0}\narc: x\ndate: {1}\n\n"
        "## Where we are\n{2}\n"
    ).format(mode, date, where or "(state not distilled — fill before spawning)")
    path = ws / "handoff-{0}.md".format(date)
    path.write_text(body, encoding="utf-8")
    return path


# --- handoff inspection -----------------------------------------------------

def test_latest_handoff_picks_newest_by_date(tmp_control_home):
    arc = _make_arc(tmp_control_home, "01-thread")
    _write_handoff(arc, date="2026-06-20", mode="continue")
    newest = _write_handoff(arc, date="2026-06-25", mode="close")
    assert go.latest_handoff(arc) == newest
    assert go.handoff_mode(newest) == "close"


def test_handoff_oneliner_reads_where_we_are(tmp_control_home):
    arc = _make_arc(tmp_control_home, "01-thread")
    h = _write_handoff(arc, date="2026-06-25", mode="continue", where="picking up the factory build")
    assert go.handoff_oneliner(h) == "picking up the factory build"


def test_handoff_oneliner_empty_on_placeholder(tmp_control_home):
    arc = _make_arc(tmp_control_home, "01-thread")
    h = _write_handoff(arc, date="2026-06-25", mode="continue")  # default placeholder
    assert go.handoff_oneliner(h) == ""


# --- resume classification (the core logic) ---------------------------------

def test_continue_handoff_is_resumable_seeded_from_distil(tmp_control_home):
    arc = _make_arc(tmp_control_home, "01-thread")
    _write_handoff(arc, date="2026-06-25", mode="continue", where="mid factory build")
    threads = go.resumable_threads(tmp_control_home)
    assert len(threads) == 1
    t = threads[0]
    assert t.kind == go.KIND_CONTINUE
    assert t.handoff is not None
    assert t.summary == "mid factory build"


def test_close_handoff_is_hidden(tmp_control_home):
    arc = _make_arc(tmp_control_home, "01-thread")
    _write_handoff(arc, date="2026-06-25", mode="close")
    assert go.resumable_threads(tmp_control_home) == []


def test_no_handoff_is_raw_from_passport(tmp_control_home):
    _make_arc(tmp_control_home, "01-thread", goal="raise me raw")
    threads = go.resumable_threads(tmp_control_home)
    assert len(threads) == 1
    t = threads[0]
    assert t.kind == go.KIND_RAW
    assert t.handoff is None
    assert t.summary == "raise me raw"


def test_continue_overrides_when_latest_even_if_an_earlier_close(tmp_control_home):
    # latest handoff wins: an old close then a fresh continue → resumable continue
    arc = _make_arc(tmp_control_home, "01-thread")
    _write_handoff(arc, date="2026-06-20", mode="close")
    _write_handoff(arc, date="2026-06-25", mode="continue", where="back on it")
    threads = go.resumable_threads(tmp_control_home)
    assert [t.kind for t in threads] == [go.KIND_CONTINUE]


# --- menu rendering ---------------------------------------------------------

def test_render_resume_menu_lists_threads(tmp_control_home):
    arc = _make_arc(tmp_control_home, "01-thread")
    _write_handoff(arc, date="2026-06-25", mode="continue", where="where line")
    menu = go.render_resume_menu(go.resumable_threads(tmp_control_home))
    assert "Resume" in menu
    assert "01-thread" in menu
    assert "[continue]" in menu
    assert "where line" in menu


def test_render_resume_menu_empty_steers_to_new(tmp_control_home):
    assert "tide go --mode new" in go.render_resume_menu([])


def test_render_new_menu_has_just_chat_at_zero(tmp_control_home):
    _make_arc(tmp_control_home, "01-thread", goal="g1")
    menu = go.render_new_menu(go.new_options(tmp_control_home), tmp_control_home)
    assert "0) just chat" in menu
    assert "1) 01-thread" in menu
    assert "g1" in menu


# --- selection parsing ------------------------------------------------------

def test_parse_pick_valid_and_range():
    assert go.parse_pick("2", 3) == 2
    assert go.parse_pick("0", 3, allow_zero=True) == 0


def test_parse_pick_rejects_zero_without_allow():
    import pytest

    with pytest.raises(go.GoError):
        go.parse_pick("0", 3)


def test_parse_pick_rejects_out_of_range_and_garbage():
    import pytest

    with pytest.raises(go.GoError):
        go.parse_pick("9", 3)
    with pytest.raises(go.GoError):
        go.parse_pick("x", 3)


# --- seed resolution --------------------------------------------------------

def test_build_resume_seed_wraps_distil_with_head_pointer():
    out = go.build_resume_seed("my-arc", "## Where we are\nhalfway there")
    assert "resume thread: my-arc" in out
    assert "MIGRATE.md" in out  # head-role pointer
    assert "halfway there" in out


def test_seed_for_thread_dry_run_returns_placeholder(tmp_control_home):
    arc = _make_arc(tmp_control_home, "01-thread")
    _write_handoff(arc, date="2026-06-25", mode="continue", where="x")
    t = go.resumable_threads(tmp_control_home)[0]
    assert go.seed_for_thread(tmp_control_home, t, dry_run=True) == "<seed-file>"


# --- CLI dry-run wiring -----------------------------------------------------

def test_cli_go_dry_run_overview_prints_both_menus(tmp_control_home, monkeypatch, capsys):
    from tide import cli

    arc = _make_arc(tmp_control_home, "01-thread", goal="factory")
    _write_handoff(arc, date="2026-06-25", mode="continue", where="mid build")
    _make_arc(tmp_control_home, "02-other", goal="other work")
    monkeypatch.chdir(tmp_control_home)

    rc = cli.main(["go", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Resume" in out and "New" in out
    assert "[continue]" in out  # the resumable thread is classified
    assert "just chat" in out


def test_cli_go_resume_pick_dry_run_delegates_to_terminal(tmp_control_home, monkeypatch, capsys):
    from tide import cli

    arc = _make_arc(tmp_control_home, "01-thread", goal="factory")
    _write_handoff(arc, date="2026-06-25", mode="continue", where="mid build")
    (tmp_control_home / "MIGRATE.md").write_text("# migrate", encoding="utf-8")
    monkeypatch.chdir(tmp_control_home)

    rc = cli.main(["go", "--mode", "resume", "--pick", "1", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    # delegated to `tide terminal` — its scoped argv shows, nothing exec'd
    assert "would resume [continue] 01-thread" in out
    assert "--strict-mcp-config" in out
    assert "--dangerously-skip-permissions" in out
    # auth-preserving: the built command line itself never carries --bare
    cmd_line = next(ln for ln in out.splitlines() if "command:" in ln)
    assert "--bare" not in cmd_line


def test_cli_go_new_just_chat_dry_run_uses_migrate_head(tmp_control_home, monkeypatch, capsys):
    from tide import cli

    _make_arc(tmp_control_home, "01-thread")
    (tmp_control_home / "MIGRATE.md").write_text("# migrate", encoding="utf-8")
    monkeypatch.chdir(tmp_control_home)

    rc = cli.main(["go", "--mode", "new", "--pick", "0", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "just chat" in out
    assert "MIGRATE.md" in out  # the plain head seed terminal resolves
