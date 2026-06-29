"""Two-stage handoff queue — offer (stage 1) → confirmed pickup (stage 2)."""

from __future__ import annotations

import io

import pytest

from tide import cli, handoff_queue as hq, paths


# --- pure operations -------------------------------------------------------

def test_offer_writes_an_offered_record(tmp_control_home):
    path = hq.offer(tmp_control_home, "stabilize-tide", arc="01-x", project="tide",
                    seed="/s/seed.md", from_session="aaa")
    assert path.is_file()
    recs = hq.list_offers(tmp_control_home)
    assert len(recs) == 1
    r = recs[0]
    assert r["status"] == hq.STATUS_OFFERED
    assert r["project"] == "tide" and r["arc"] == "01-x"
    assert r["seed"] == "/s/seed.md"


def test_confirm_for_project_claims_newest_and_stamps(tmp_control_home):
    hq.offer(tmp_control_home, "old", arc="-", project="tide", seed="/s/a.md")
    hq.offer(tmp_control_home, "new", arc="-", project="tide", seed="/s/b.md")
    claimed = hq.confirm_for_project(tmp_control_home, "tide", session="sess-123")
    assert claimed is not None
    assert claimed["slug"] == "new"           # newest offered claimed
    assert claimed["status"] == hq.STATUS_TAKEN
    assert claimed["taken_by"] == "sess-123"
    # the older one is still offered
    offered = hq.list_offers(tmp_control_home, status=hq.STATUS_OFFERED)
    assert [r["slug"] for r in offered] == ["old"]


def test_confirm_for_project_noop_when_nothing_pending(tmp_control_home):
    hq.offer(tmp_control_home, "x", arc="-", project="other", seed="-")
    assert hq.confirm_for_project(tmp_control_home, "tide") is None  # different project


def test_take_by_key_marks_taken(tmp_control_home):
    hq.offer(tmp_control_home, "ship-it", arc="-", project="p", seed="-")
    rec = hq.take(tmp_control_home, "ship-it", session="s")
    assert rec["status"] == hq.STATUS_TAKEN


def test_take_unknown_key_raises(tmp_control_home):
    with pytest.raises(hq.HandoffError, match="no offer matching"):
        hq.take(tmp_control_home, "ghost")


# --- CLI + hook ------------------------------------------------------------

def test_cli_offer_then_confirm_hook_flips_status(tmp_control_home, tmp_path, monkeypatch):
    from tide.init_home import scaffold_project

    proj = tmp_path / "tide"
    proj.mkdir()
    scaffold_project(proj, name="tide")
    monkeypatch.setenv("TIDE_HOME", str(tmp_control_home))

    # stage 1: offer (from anywhere — resolves the control-home via TIDE_HOME)
    assert cli.main(["handoffs", "offer", "cont", "--project", "tide", "--seed", "/s.md"]) == 0
    assert hq.list_offers(tmp_control_home, status=hq.STATUS_OFFERED)

    # stage 2: the UserPromptSubmit hook fires in the picked-up session (cwd = project).
    # The first message confirms — claim is by cwd-project match (stdin session id is a
    # best-effort audit field; the pure-function test above covers its stamping).
    monkeypatch.chdir(proj)
    monkeypatch.setattr("sys.stdin", io.StringIO('{"session_id": "new-sess"}'))
    assert cli.main(["hook", "handoff-confirm"]) == 0

    offered = hq.list_offers(tmp_control_home, status=hq.STATUS_OFFERED)
    taken = hq.list_offers(tmp_control_home, status=hq.STATUS_TAKEN)
    assert not offered and len(taken) == 1  # offered → taken on first message


def test_confirm_hook_is_silent_noop_with_nothing_pending(tmp_project, monkeypatch):
    # A hook must never break an ordinary session: no offers → exit 0, no claim.
    monkeypatch.setenv("TIDE_HOME", str(tmp_project))
    monkeypatch.chdir(tmp_project)
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    assert cli.main(["hook", "handoff-confirm"]) == 0


def test_menu_banner_surfaces_pending_handoffs(tmp_control_home):
    from tide.launcher import menu

    hq.offer(tmp_control_home, "cont", arc="01-x", project="tide-stack", seed="/s/seed.md")
    entries = [{"name": "tide-stack", "path": "/p/tide-stack"}]
    banner = menu.render_pending_handoffs(tmp_control_home, entries)
    assert "pending handoffs" in banner
    assert "01-cont" in banner and "tide-stack" in banner
    assert "/p/tide-stack" in banner and "/s/seed.md" in banner  # actionable pickup cmd


def test_menu_banner_empty_when_nothing_offered(tmp_control_home):
    from tide.launcher import menu

    assert menu.render_pending_handoffs(tmp_control_home, []) == ""


def test_navigate_interactive_handoff_pick(monkeypatch):
    from tide.launcher import menu, select

    monkeypatch.setattr(select, "select", lambda *a, **k: 0)  # pick first row = handoff
    rec = {"slug": "stab", "project": "p", "mode": "continue"}
    res = menu.navigate_interactive([{"name": "p", "path": "/p"}], handoffs=[rec])
    assert res[0] == menu.HANDOFF_PICK and res[1] is rec


def test_launch_handoff_seeds_but_stays_offered_until_confirmed(tmp_control_home, tmp_path):
    from tide.launcher import menu
    from tide.adapters import SpawnResult
    from tide.init_home import scaffold_project

    proj = tmp_path / "tide-stack"
    proj.mkdir()
    scaffold_project(proj, name="tide-stack")
    seed = tmp_path / "seed.md"
    seed.write_text("# distil\n", encoding="utf-8")
    hq.offer(tmp_control_home, "stab", arc="01-x", project="tide-stack", seed=str(seed))
    rec = hq.list_offers(tmp_control_home)[0]
    entries = [{"name": "tide-stack", "path": str(proj)}]

    captured = {}

    class FakeAdapter:
        def spawn(self, *, command, cwd, title, dry_run):
            captured["command"] = command
            captured["cwd"] = cwd
            return SpawnResult(ok=True, detail="spawned", commands=[command])

    res = menu.launch_handoff(
        rec, entries, control_home=tmp_control_home, adapter=FakeAdapter(), dry_run=False
    )
    assert res.ok
    assert str(seed) in " ".join(captured["command"])   # session seeded from the distil
    assert captured["cwd"] == str(proj)
    # CRITICAL: launching does NOT consume the offer — it stays OFFERED until the
    # picked-up session's first message confirms it (the confirm hook).
    assert hq.list_offers(tmp_control_home, status=hq.STATUS_OFFERED)
    assert not hq.list_offers(tmp_control_home, status=hq.STATUS_TAKEN)


def test_launch_handoff_pins_session_id_for_menu_resume(tmp_control_home, tmp_path):
    # After pickup the session must be RESUMABLE from the menu: the new claude
    # session id is pinned onto the handoff's target session passport.
    from tide.launcher import menu
    from tide.adapters import SpawnResult
    from tide import fields
    from tide.init_home import scaffold_project

    proj = tmp_path / "tide-stack"
    proj.mkdir()
    scaffold_project(proj, name="tide-stack")
    # a session dir with input/<seed> + arc.md (the handoff's target shape)
    sess = proj / ".tide" / "arcs" / "01-@prz" / "arcs" / "01-session"
    (sess / "input").mkdir(parents=True)
    (sess / "arc.md").write_text("# 01-session\nstatus: active\n", encoding="utf-8")
    seed = sess / "input" / "handoff-seed.md"
    seed.write_text("# distil\n", encoding="utf-8")
    hq.offer(tmp_control_home, "stab", arc="01-@prz/01-session", project="tide-stack", seed=str(seed))
    rec = hq.list_offers(tmp_control_home)[0]

    class FakeAdapter:
        def spawn(self, *, command, cwd, title, dry_run):
            return SpawnResult(ok=True, detail="spawned", commands=[command])

    menu.launch_handoff(
        rec, [{"name": "tide-stack", "path": str(proj)}],
        control_home=tmp_control_home, adapter=FakeAdapter(), dry_run=False,
    )
    pinned = fields.read_field(sess / "arc.md", "claude-session")
    assert pinned and len(pinned) > 10  # a uuid was stamped → menu can --resume it


def test_install_hooks_wires_user_prompt_submit(tmp_project):
    from tide.hooks.install import install_hooks, HANDOFF_CONFIRM_CMD, USER_PROMPT_EVENT
    import json

    path, notes = install_hooks(tmp_project)
    data = json.loads(path.read_text(encoding="utf-8"))
    cmds = [
        h.get("command")
        for g in data["hooks"][USER_PROMPT_EVENT]
        for h in g.get("hooks", [])
    ]
    assert HANDOFF_CONFIRM_CMD in cmds
