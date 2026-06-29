"""Tests for tide.adopt — one-command project onboarding.

git + orca steps are stubbed (monkeypatch subprocess.run / shutil.which); the
control-home is a tmp dir pointed at via $TIDE_HOME so the roster step lands
without touching the real machine.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.conftest import build_tide_skeleton
from tide import adopt, paths, roster


def _cp(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    """A tmp control-home, exported via $TIDE_HOME so roster.add resolves it."""
    ch = tmp_path / "home"
    ch.mkdir()
    build_tide_skeleton(ch, name="home", control_home=True)
    monkeypatch.setenv(paths.TIDE_HOME_ENV, str(ch))
    return ch


@pytest.fixture
def target(tmp_path: Path) -> Path:
    d = tmp_path / "myproj"
    d.mkdir()
    return d


# --- core happy path -------------------------------------------------------

def test_adopt_scaffolds_tide_and_rosters(home, target, monkeypatch):
    git_calls = []
    orca_calls = []

    def fake_run(argv, **kwargs):
        if argv[:1] == ["git"]:
            git_calls.append(argv)
        elif argv[:1] == ["orca"]:
            orca_calls.append(argv)
        return _cp()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/orca")

    report = adopt.adopt(target, name="demo")

    # .tide/ scaffolded
    assert paths.tide_dir(target).is_dir()
    assert report.step("tide").status == adopt.DONE

    # git init invoked with the resolved abs path
    assert report.step("git").status == adopt.DONE
    assert git_calls and git_calls[0][:2] == ["git", "init"]
    assert str(target.resolve()) in git_calls[0]

    # orca repo add --path <abs> --json invoked
    assert report.step("orca").status == adopt.DONE
    assert orca_calls == [["orca", "repo", "add", "--path", str(target.resolve()), "--json"]]

    # rostered into the control-home
    assert report.step("roster").status == adopt.DONE
    entries = roster.read_roster(home)
    assert {"name": "demo", "path": str(target.resolve())} in entries


def test_name_defaults_to_basename(home, target, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _cp())
    monkeypatch.setattr(shutil, "which", lambda name: None)
    report = adopt.adopt(target)
    assert report.name == "myproj"


# --- opt-outs --------------------------------------------------------------

def test_no_git_skips_git(home, target, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: calls.append(argv) or _cp())
    monkeypatch.setattr(shutil, "which", lambda name: None)

    report = adopt.adopt(target, do_git=False)
    assert report.step("git").status == adopt.SKIPPED
    assert not any(c[:1] == ["git"] for c in calls)


def test_no_orca_skips_orca(home, target, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: calls.append(argv) or _cp())
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/orca")

    report = adopt.adopt(target, do_orca=False)
    assert report.step("orca").status == adopt.SKIPPED
    assert not any(c[:1] == ["orca"] for c in calls)


def test_orca_absent_skips_with_note(home, target, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _cp())
    monkeypatch.setattr(shutil, "which", lambda name: None)
    report = adopt.adopt(target)
    step = report.step("orca")
    assert step.status == adopt.SKIPPED
    assert "PATH" in step.detail


def test_git_missing_warns_and_continues(home, target, monkeypatch):
    def fake_run(argv, **kwargs):
        if argv[:1] == ["git"]:
            raise FileNotFoundError("git")
        return _cp()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    report = adopt.adopt(target)
    assert report.step("git").status == adopt.WARN
    # the rest still ran
    assert paths.tide_dir(target).is_dir()
    assert report.step("roster").status == adopt.DONE


def test_orca_already_registered_is_success(home, target, monkeypatch):
    def fake_run(argv, **kwargs):
        if argv[:1] == ["orca"]:
            raise subprocess.CalledProcessError(returncode=1, cmd=argv, stderr="already added")
        return _cp()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/orca")

    report = adopt.adopt(target)
    assert report.step("orca").status == adopt.DONE


# --- no control-home -------------------------------------------------------

def test_no_control_home_skips_roster_gracefully(tmp_path, monkeypatch):
    # No $TIDE_HOME, and cwd has no .tide ancestor → control_home() raises, so the
    # roster step is skipped (not a hard failure). chdir to the clean tmp parent so
    # the cwd-climb fallback finds nothing (the adopted child's .tide is below cwd).
    target = tmp_path / "myproj"
    target.mkdir()
    monkeypatch.delenv(paths.TIDE_HOME_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _cp())
    monkeypatch.setattr(shutil, "which", lambda name: None)

    report = adopt.adopt(target)
    step = report.step("roster")
    assert step.status == adopt.SKIPPED
    assert "TIDE_HOME" in step.detail
    # scaffolding still happened
    assert paths.tide_dir(target).is_dir()


# --- idempotency -----------------------------------------------------------

def test_rerun_is_noop_ish_success(home, target, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _cp())
    monkeypatch.setattr(shutil, "which", lambda name: None)

    adopt.adopt(target, name="demo")
    # second run: .tide/ already there, roster replaces in place (no dup)
    report = adopt.adopt(target, name="demo")
    assert report.step("tide").status == adopt.SKIPPED
    entries = [e for e in roster.read_roster(home) if e["name"] == "demo"]
    assert len(entries) == 1


# --- rendering -------------------------------------------------------------

def test_render_report_has_ready_line(home, target, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _cp())
    monkeypatch.setattr(shutil, "which", lambda name: None)
    report = adopt.adopt(target, name="demo")
    out = adopt.render_report(report)
    assert "ready: tide menu → demo" in out
