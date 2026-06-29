"""U5 unit — roster status extension: active / archived.

A project's third field carries optional ``key=value`` tags (e.g.
``status=archived`` and/or ``env=box``).  ``status`` defaults to ``active`` and
is stored as a dict key ONLY when archived — mirroring the optional
``environment`` key.  All existing 2-field and legacy bare-``env`` behaviour
stays byte-for-byte identical (only an archived entry ever emits the tag form).
"""

from __future__ import annotations

import pytest

from tide import paths, roster


# --- parse -----------------------------------------------------------------

def test_parse_plain_line_has_no_status_key():
    entry = roster._parse_line("focus | /p/focus")
    assert entry == {"name": "focus", "path": "/p/focus"}
    assert "status" not in entry


def test_parse_legacy_bare_env_still_has_no_status():
    entry = roster._parse_line("bb | /p/bb | box")
    assert entry == {"name": "bb", "path": "/p/bb", "environment": "box"}
    assert "status" not in entry


def test_parse_status_tag_sets_status_archived():
    entry = roster._parse_line("old | /p/old | status=archived")
    assert entry == {"name": "old", "path": "/p/old", "status": "archived"}


def test_parse_env_and_status_tags_together():
    entry = roster._parse_line("rem | /p/rem | env=box status=archived")
    assert entry == {
        "name": "rem",
        "path": "/p/rem",
        "environment": "box",
        "status": "archived",
    }


def test_parse_explicit_active_tag_omits_status_key():
    # status=active is the default → no key, so dict-equality with old shapes holds
    entry = roster._parse_line("a | /p/a | status=active")
    assert entry == {"name": "a", "path": "/p/a"}


# --- add -------------------------------------------------------------------

def test_add_archived_stores_status(tmp_control_home):
    roster.add(tmp_control_home, "old", "/p/old", status="archived")
    assert roster.read_roster(tmp_control_home) == [
        {"name": "old", "path": "/p/old", "status": "archived"}
    ]


def test_add_active_omits_status_key(tmp_control_home):
    roster.add(tmp_control_home, "focus", "/p/focus", status="active")
    entry = roster.read_roster(tmp_control_home)[0]
    assert "status" not in entry


def test_add_re_archives_and_un_archives_in_place(tmp_control_home):
    roster.add(tmp_control_home, "focus", "/p/focus")
    roster.add(tmp_control_home, "focus", "/p/focus", status="archived")
    assert roster.read_roster(tmp_control_home)[0]["status"] == "archived"
    # adding again without status reverts to active (clears the key)
    roster.add(tmp_control_home, "focus", "/p/focus")
    assert "status" not in roster.read_roster(tmp_control_home)[0]


def test_add_env_and_status_together(tmp_control_home):
    roster.add(tmp_control_home, "rem", "/p/rem", env="box", status="archived")
    assert roster.read_roster(tmp_control_home) == [
        {"name": "rem", "path": "/p/rem", "environment": "box", "status": "archived"}
    ]


# --- render / round-trip ---------------------------------------------------

def test_render_archived_uses_status_tag():
    text = roster._render([{"name": "old", "path": "/p/old", "status": "archived"}])
    assert "old | /p/old | status=archived" in text


def test_render_env_and_status_uses_both_tags():
    text = roster._render(
        [{"name": "rem", "path": "/p/rem", "environment": "box", "status": "archived"}]
    )
    assert "rem | /p/rem | env=box status=archived" in text


def test_render_active_with_env_stays_legacy_bare(tmp_control_home):
    # an active remote entry MUST still render as the legacy bare-env form
    roster.add(tmp_control_home, "bb", "/p/bb", env="box")
    text = paths.roster_file(tmp_control_home).read_text(encoding="utf-8")
    assert text == "# tide roster\nbb | /p/bb | box\n"


def test_set_status_archives_existing(tmp_control_home):
    roster.add(tmp_control_home, "focus", "/p/focus")
    roster.set_status(tmp_control_home, "focus", "archived")
    assert roster.read_roster(tmp_control_home)[0]["status"] == "archived"


def test_set_status_restores_to_active(tmp_control_home):
    roster.add(tmp_control_home, "focus", "/p/focus", status="archived")
    roster.set_status(tmp_control_home, "focus", "active")
    assert "status" not in roster.read_roster(tmp_control_home)[0]


def test_set_status_absent_project_raises(tmp_control_home):
    with pytest.raises(roster.RosterError):
        roster.set_status(tmp_control_home, "ghost", "archived")


def test_set_status_invalid_raises(tmp_control_home):
    roster.add(tmp_control_home, "focus", "/p/focus")
    with pytest.raises(roster.RosterError):
        roster.set_status(tmp_control_home, "focus", "frozen")


def test_set_status_preserves_path_and_env(tmp_control_home):
    roster.add(tmp_control_home, "bb", "/p/bb", env="box")
    roster.set_status(tmp_control_home, "bb", "archived")
    assert roster.read_roster(tmp_control_home)[0] == {
        "name": "bb",
        "path": "/p/bb",
        "environment": "box",
        "status": "archived",
    }


def test_archived_round_trips(tmp_control_home):
    roster.add(tmp_control_home, "focus", "/p/focus")
    roster.add(tmp_control_home, "old", "/p/old", status="archived")
    entries = roster.read_roster(tmp_control_home)
    assert entries == [
        {"name": "focus", "path": "/p/focus"},
        {"name": "old", "path": "/p/old", "status": "archived"},
    ]
