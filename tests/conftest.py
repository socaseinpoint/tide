"""Shared pytest fixtures for the tide suite.

``tmp_project`` builds a minimal per-project ``.tide/`` skeleton in a tmp dir,
matching the blueprint ``tide_dir_format``. Later units (arc/cannon/contract)
build their integration + e2e tests on top of it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

CANON_MD_TEMPLATE = """# CANON.md — {name}

## What it is

## State & components

## Interfaces / how used

## Cannon journal
"""


def build_tide_skeleton(root: Path, *, name: str, control_home: bool = False) -> Path:
    """Create a ``.tide/`` skeleton under *root* and return the .tide path.

    Layout (per blueprint tide_dir_format):
      .tide/cannon/CANON.md   — living-IS doc
      .tide/cannon/config     — lang=en
      .tide/arcs/             — work stream (NN-<slug>/ entries land here)
      .tide/arcs/candidates/  — separately-numbered candidate backlog
      .tide/state/strictness  — per-project dial (default 'strict')

    A control-home additionally gets a top-level roster.md ('name | path' lines).
    """
    tide = root / ".tide"
    cannon = tide / "cannon"
    arcs = tide / "arcs"
    state = tide / "state"
    for d in (cannon, arcs, arcs / "candidates", state):
        d.mkdir(parents=True, exist_ok=True)

    (cannon / "CANON.md").write_text(CANON_MD_TEMPLATE.format(name=name), encoding="utf-8")
    (cannon / "config").write_text("lang=en\n", encoding="utf-8")
    (state / "strictness").write_text("strict\n", encoding="utf-8")

    if control_home:
        (root / "roster.md").write_text("# tide roster\n", encoding="utf-8")

    return tide


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """A tmp dir with a fresh ``.tide/`` skeleton; returns the project root."""
    build_tide_skeleton(tmp_path, name="demo")
    return tmp_path


@pytest.fixture
def tmp_control_home(tmp_path: Path) -> Path:
    """A tmp control-home: ``.tide/`` skeleton + roster.md (dogfood install dir)."""
    build_tide_skeleton(tmp_path, name="control-home", control_home=True)
    return tmp_path


@pytest.fixture
def worker_role(monkeypatch) -> None:
    """Force TIDE_ROLE=worker for role-gating tests."""
    monkeypatch.setenv("TIDE_ROLE", "worker")


@pytest.fixture
def orchestrator_role(monkeypatch) -> None:
    """Force TIDE_ROLE=orchestrator for role-gating tests."""
    monkeypatch.setenv("TIDE_ROLE", "orchestrator")
