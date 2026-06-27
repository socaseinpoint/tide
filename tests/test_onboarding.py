"""C2 — onboarding: peripheral first-run walkthrough (pass-or-skip; skip == passed).

The whole add-on lives in :mod:`tide.onboarding`. These tests pin the contract the
human signed: exactly TWO states (passed / not-passed), a binary marker under
``.tide/state/``, a re-runnable walkthrough, and a session-start nudge that goes
silent once passed and never breaks a session.
"""

from __future__ import annotations

import builtins

import pytest

from tide import cli, paths, readme
from tide.arc import stream
from tide.hooks import session_start
from tide.onboarding import commands, flow, state


# ---------------------------------------------------------------------------
# Marker: two-state (passed / not-passed), nothing in between
# ---------------------------------------------------------------------------

def test_marker_absent_reads_not_passed(tmp_project):
    assert state.is_passed(tmp_project) is False


def test_marker_lives_under_state_dir(tmp_project):
    assert state.marker_path(tmp_project) == paths.state_dir(tmp_project) / "onboarding"


def test_mark_passed_writes_marker(tmp_project):
    state.mark_passed(tmp_project)
    assert state.is_passed(tmp_project) is True
    assert state.marker_path(tmp_project).is_file()


def test_mark_passed_creates_state_dir_when_missing(tmp_path):
    # A bare dir with no .tide/state/ — mark_passed must create the dir (atomic_write).
    state.mark_passed(tmp_path)
    assert state.is_passed(tmp_path) is True


def test_mark_passed_is_idempotent(tmp_project):
    state.mark_passed(tmp_project)
    first = state.marker_path(tmp_project).read_text(encoding="utf-8")
    state.mark_passed(tmp_project)
    assert state.marker_path(tmp_project).read_text(encoding="utf-8") == first


def test_reset_removes_marker(tmp_project):
    state.mark_passed(tmp_project)
    assert state.reset(tmp_project) is True
    assert state.is_passed(tmp_project) is False


def test_reset_idempotent_when_absent(tmp_project):
    assert state.reset(tmp_project) is False


# ---------------------------------------------------------------------------
# Two-state proof: skip and complete leave IDENTICAL bytes on disk
# ---------------------------------------------------------------------------

def test_skip_and_complete_write_identical_marker(tmp_path):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    commands.run_walkthrough(a, input_fn=lambda *_: "", output_fn=lambda *_: None)      # completes
    commands.run_walkthrough(b, input_fn=lambda *_: "skip", output_fn=lambda *_: None)  # skips at step 1
    assert state.is_passed(a) and state.is_passed(b)
    # The on-disk payload does NOT encode a distinct 'skipped' state — only two states exist.
    assert state.marker_path(a).read_text(encoding="utf-8") == state.marker_path(b).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Flow content (pure, no I/O)
# ---------------------------------------------------------------------------

def test_steps_cover_the_first_project_flow():
    blob = " ".join("{0} {1}".format(t, b) for t, b in flow.steps()).lower()
    for token in ("tide terminal", "vector", "canon", "arc", "handoff", "land"):
        assert token in blob, "walkthrough must teach the '{0}' beat".format(token)


def test_render_step_is_pure_numbered_text():
    s = flow.render_step(2, 5, "A Title", "A body line.")
    assert "A Title" in s and "A body line." in s and "2/5" in s


# ---------------------------------------------------------------------------
# Walkthrough: PASS or SKIP both mark passed (skip == passed)
# ---------------------------------------------------------------------------

def test_walkthrough_complete_marks_passed(tmp_project):
    how = commands.run_walkthrough(tmp_project, input_fn=lambda *_: "", output_fn=lambda *_: None)
    assert how == "passed"
    assert state.is_passed(tmp_project) is True


def test_walkthrough_skip_marks_passed(tmp_project):
    how = commands.run_walkthrough(tmp_project, input_fn=lambda *_: "skip", output_fn=lambda *_: None)
    assert how == "skipped"               # UX label only
    assert state.is_passed(tmp_project) is True  # ...but the STATE is passed


def test_walkthrough_emits_every_step(tmp_project):
    out: list = []
    commands.run_walkthrough(tmp_project, input_fn=lambda *_: "", output_fn=out.append)
    blob = "\n".join(out)
    for n in range(1, len(flow.steps()) + 1):
        assert "{0}/{1}".format(n, len(flow.steps())) in blob


def test_safe_input_returns_empty_on_eof(monkeypatch):
    def boom(*_a, **_k):
        raise EOFError
    monkeypatch.setattr(builtins, "input", boom)
    assert commands._safe_input("prompt ") == ""


# ---------------------------------------------------------------------------
# CLI: tide onboarding  (+ --status / --reset / reinvocation)
# ---------------------------------------------------------------------------

def test_cli_onboarding_runs_and_marks_passed(tmp_project, monkeypatch):
    monkeypatch.chdir(tmp_project)
    monkeypatch.setattr(builtins, "input", lambda *_a, **_k: "")  # advance through
    rc = cli.main(["onboarding"])
    assert rc == 0
    assert state.is_passed(tmp_project) is True


def test_cli_onboarding_status_reports_two_states(tmp_project, monkeypatch, capsys):
    monkeypatch.chdir(tmp_project)
    cli.main(["onboarding", "--status"])
    assert capsys.readouterr().out.strip() == "not-passed"
    state.mark_passed(tmp_project)
    cli.main(["onboarding", "--status"])
    assert capsys.readouterr().out.strip() == "passed"


def test_cli_onboarding_reset_clears_marker(tmp_project, monkeypatch, capsys):
    monkeypatch.chdir(tmp_project)
    state.mark_passed(tmp_project)
    rc = cli.main(["onboarding", "--reset"])
    assert rc == 0
    assert state.is_passed(tmp_project) is False
    assert "reset" in capsys.readouterr().out.lower()


def test_cli_onboarding_is_reinvocable_after_passed(tmp_project, monkeypatch, capsys):
    monkeypatch.chdir(tmp_project)
    monkeypatch.setattr(builtins, "input", lambda *_a, **_k: "")
    state.mark_passed(tmp_project)
    rc = cli.main(["onboarding"])  # re-run even though already passed
    assert rc == 0
    assert "already" in capsys.readouterr().out.lower()
    assert state.is_passed(tmp_project) is True  # stays passed


# ---------------------------------------------------------------------------
# Nudge: surfaced on first run, silent once passed
# ---------------------------------------------------------------------------

def test_nudge_fires_when_not_passed(tmp_project):
    lines = commands.nudge(tmp_project)
    assert lines and "onboarding" in lines[0].lower()


def test_nudge_is_one_line(tmp_project):
    assert len(commands.nudge(tmp_project)) == 1


def test_nudge_silent_once_passed(tmp_project):
    state.mark_passed(tmp_project)
    assert commands.nudge(tmp_project) == []


# ---------------------------------------------------------------------------
# Session-start integration (the ONE core touch-point in the hook)
# ---------------------------------------------------------------------------

def _quiet_project(root):
    """Silence every OTHER advisory so only the onboarding nudge can show."""
    stream.new_arc(root, "do-thing")  # suppress arc-first
    readme.generate(root)             # suppress readme-drift


def test_session_start_surfaces_nudge_on_first_run(tmp_project):
    _quiet_project(tmp_project)
    text = session_start.render(tmp_project, "orchestrator")
    assert "tide onboarding" in text


def test_session_start_nudge_silent_once_passed(tmp_project):
    _quiet_project(tmp_project)
    state.mark_passed(tmp_project)
    text = session_start.render(tmp_project, "orchestrator")
    assert "tide onboarding" not in text


def test_session_start_nudge_never_breaks_a_session(tmp_project, monkeypatch):
    # If the onboarding add-on explodes, the hook swallows it and still renders.
    import tide.onboarding as ob

    def boom(*_a, **_k):
        raise RuntimeError("onboarding blew up")

    monkeypatch.setattr(ob, "nudge", boom)
    text = session_start.render(tmp_project, "worker")  # must NOT raise
    assert isinstance(text, str)
    assert "tide onboarding" not in text
