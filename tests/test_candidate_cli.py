"""U4 integration — `tide candidate …` wired through the real CLI parser."""

from __future__ import annotations

import pytest

from tide import cli, fields, paths


@pytest.fixture
def in_project(tmp_project, monkeypatch):
    """Run CLI commands as if cwd is the project root (paths resolves from cwd)."""
    monkeypatch.chdir(tmp_project)
    return tmp_project


def test_cli_candidate_add_captures_file(in_project):
    rc = cli.main(["candidate", "add", "batch writes", "--from", "alpha", "do", "it"])
    assert rc == 0
    path = paths.candidates_dir(in_project) / "01-batch-writes.md"
    assert path.is_file()
    assert fields.read_field(path, "from") == "alpha"
    assert "do it" in path.read_text(encoding="utf-8")


def test_cli_candidate_add_long_idea_caps_slug_keeps_body(in_project):
    # fix F6: a single long pasted idea → short slug handle + full idea in body.
    idea = "make the export button stream rows so a huge sheet does not freeze the tab"
    rc = cli.main(["candidate", "add", idea])
    assert rc == 0
    files = list(paths.candidates_dir(in_project).glob("*.md"))
    assert len(files) == 1
    path = files[0]
    stem_slug = path.stem.split("-", 1)[1]
    assert len(stem_slug) <= 48
    assert idea in path.read_text(encoding="utf-8")


def test_cli_candidate_list_renders(in_project, capsys):
    cli.main(["candidate", "add", "one"])
    rc = cli.main(["candidate", "list"])
    assert rc == 0
    assert "01-one" in capsys.readouterr().out


def test_cli_candidate_promote_refused_for_worker(in_project, worker_role, capsys):
    cli.main(["candidate", "add", "idea"])
    rc = cli.main(["candidate", "promote", "idea"])
    assert rc == 1  # RoleError → nonzero
    assert "orchestrator-only" in capsys.readouterr().err
    # candidate untouched, no arc created
    assert (paths.candidates_dir(in_project) / "01-idea.md").is_file()
    assert not (paths.arcs_dir(in_project) / "01-idea").exists()


def test_cli_candidate_promote_runs_for_orchestrator(in_project, orchestrator_role):
    cli.main(["candidate", "add", "idea", "--from", "alpha"])
    rc = cli.main(["candidate", "promote", "idea"])
    assert rc == 0
    entry = paths.arcs_dir(in_project) / "01-idea"
    assert (entry / "arc.md").is_file()
    assert (entry / "input" / "01-idea.md").is_file()
    assert not (paths.candidates_dir(in_project) / "01-idea.md").exists()


def test_cli_candidate_promote_unknown_key_errors(in_project, orchestrator_role, capsys):
    rc = cli.main(["candidate", "promote", "ghost"])
    assert rc == 1
    assert "no candidate matching" in capsys.readouterr().err


def test_cli_candidate_add_into_another_rostered_project(tmp_control_home, tmp_path, monkeypatch):
    # Cross-project capture: working in project A, drop a candidate into rostered B.
    from tide import roster
    from tide.init_home import scaffold_project

    home = tmp_control_home
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    scaffold_project(a, name="a")
    scaffold_project(b, name="b")
    roster.add(home, "a", str(a))
    roster.add(home, "b", str(b))
    monkeypatch.setenv("TIDE_HOME", str(home))
    monkeypatch.chdir(a)

    rc = cli.main(["candidate", "add", "ship-it", "the", "idea", "--project", "b"])
    assert rc == 0
    landed = paths.candidates_dir(b) / "01-ship-it.md"
    assert landed.is_file()  # in B …
    assert not list(paths.candidates_dir(a).glob("*.md"))  # … NOT in A
    assert "a" in (fields.read_field(landed, "from") or "")  # tagged with the origin


def test_cli_candidate_add_unknown_project_errors(tmp_control_home, tmp_path, monkeypatch, capsys):
    from tide.init_home import scaffold_project

    a = tmp_path / "a"
    a.mkdir()
    scaffold_project(a, name="a")
    monkeypatch.setenv("TIDE_HOME", str(tmp_control_home))
    monkeypatch.chdir(a)
    rc = cli.main(["candidate", "add", "x", "--project", "ghost"])
    assert rc == 1
    assert "no project named 'ghost'" in capsys.readouterr().err
