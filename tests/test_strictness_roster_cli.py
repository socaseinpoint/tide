"""U5 integration — `tide strictness` / `tide roster …` through the real CLI."""

from __future__ import annotations

import pytest

from tide import cli, paths


@pytest.fixture
def in_project(tmp_project, monkeypatch):
    monkeypatch.chdir(tmp_project)
    return tmp_project


@pytest.fixture
def in_control_home(tmp_control_home, monkeypatch):
    monkeypatch.chdir(tmp_control_home)
    return tmp_control_home


# --- strictness ------------------------------------------------------------

def test_cli_strictness_show_default(in_project, capsys):
    rc = cli.main(["strictness"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "strict"


def test_cli_strictness_set_and_show(in_project, capsys):
    rc = cli.main(["strictness", "loose"])
    assert rc == 0
    assert "loose" in capsys.readouterr().out
    cli.main(["strictness"])
    assert capsys.readouterr().out.strip() == "loose"


def test_cli_strictness_rejects_bad_value(in_project):
    # argparse choices guard → SystemExit(2) before the handler runs.
    with pytest.raises(SystemExit):
        cli.main(["strictness", "medium"])


# --- roster ----------------------------------------------------------------

def test_cli_roster_add_ls_rm_round_trip(in_control_home, capsys):
    assert cli.main(["roster", "add", "focus", "/p/focus"]) == 0
    capsys.readouterr()
    assert cli.main(["roster", "ls"]) == 0
    assert "focus | /p/focus" in capsys.readouterr().out

    assert cli.main(["roster", "rm", "focus"]) == 0
    capsys.readouterr()
    cli.main(["roster", "ls"])
    assert "(no projects)" in capsys.readouterr().out


def test_cli_roster_rm_absent_errors(in_control_home, capsys):
    rc = cli.main(["roster", "rm", "ghost"])
    assert rc == 1
    assert "no project named" in capsys.readouterr().err
