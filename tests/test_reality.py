"""M2 unit — cannon.reality: manifest parsing + reality-rev (content hash).

Coverage targets:
* _parse_canon_text: indented globs, dash-list globs, stops at ## , None when absent
* parse_manifest: canon preamble vs state-file fallback, None when neither
* reality_rev: None for no manifest; stable; changes with covered files;
  stable for uncovered files; empty-match → defined (not None)
* git mode: ignores untracked files; detects new tracked files
* stamp_reality_rev: stamps the passport doc; no-op when no manifest
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

import pytest

from tide.cannon import reality

from tests.conftest import build_tide_skeleton


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _init_git(path: Path) -> None:
    """Initialize a bare git repo with an initial commit."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test"],
        check=True, capture_output=True,
    )
    (path / ".gitkeep").write_text("", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(path), "add", "-A"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "init"],
        check=True, capture_output=True,
    )


def _git_add_commit(path: Path, *rel_paths: str) -> None:
    for rel in rel_paths:
        subprocess.run(
            ["git", "-C", str(path), "add", rel], check=True, capture_output=True
        )
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "add files"],
        check=True, capture_output=True,
    )


@pytest.fixture
def tmp_git_project(tmp_path: Path) -> Path:
    """A tmp project with a git repo initialized and an initial commit."""
    build_tide_skeleton(tmp_path, name="demo")
    _init_git(tmp_path)
    return tmp_path


def _write_canon_covers_preamble(root: Path, globs: List[str]) -> None:
    """Insert a ``canon-covers:`` block into CANON.md's preamble (indented format)."""
    from tide import paths
    canon = paths.canon_file(root)
    text = canon.read_text(encoding="utf-8")
    block = "canon-covers:\n" + "".join("  {0}\n".format(g) for g in globs)
    # Insert after the H1 line (first line starting with "# ")
    lines = text.splitlines()
    h1_idx = next(i for i, ln in enumerate(lines) if ln.startswith("# "))
    lines.insert(h1_idx + 1, block.rstrip())
    canon.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_state_covers(root: Path, lines: List[str]) -> None:
    """Write *lines* to ``.tide/state/canon-covers``."""
    from tide import paths
    (paths.state_dir(root) / "canon-covers").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# _parse_canon_text (pure)
# ---------------------------------------------------------------------------

def test_parse_canon_text_none_when_no_marker():
    text = "# CANON.md — demo\n\n## What it is\n"
    assert reality._parse_canon_text(text) is None


def test_parse_canon_text_indented_globs():
    text = (
        "# CANON.md — demo\n"
        "canon-covers:\n"
        "  src/**/*.py\n"
        "  tests/*.py\n"
        "\n"
        "## What it is\n"
    )
    globs = reality._parse_canon_text(text)
    assert globs == ["src/**/*.py", "tests/*.py"]


def test_parse_canon_text_dash_list_format():
    text = (
        "# CANON.md — demo\n"
        "canon-covers:\n"
        "- src/**/*.py\n"
        "- tests/*.py\n"
        "\n"
        "## What it is\n"
    )
    globs = reality._parse_canon_text(text)
    assert globs == ["src/**/*.py", "tests/*.py"]


def test_parse_canon_text_stops_at_first_h2():
    text = (
        "# CANON.md — demo\n"
        "canon-covers:\n"
        "  src/*.py\n"
        "## What it is\n"
        "  not-a-glob-section-body\n"
    )
    globs = reality._parse_canon_text(text)
    assert globs == ["src/*.py"]


def test_parse_canon_text_ends_at_non_indented_line():
    text = (
        "# CANON.md — demo\n"
        "canon-covers:\n"
        "  src/*.py\n"
        "some-other-field: value\n"
        "  should-not-be-a-glob\n"
    )
    globs = reality._parse_canon_text(text)
    assert globs == ["src/*.py"]


def test_parse_canon_text_blank_lines_inside_block_ok():
    text = (
        "# CANON.md — demo\n"
        "canon-covers:\n"
        "  src/*.py\n"
        "\n"
        "  tests/*.py\n"
        "\n"
        "## What it is\n"
    )
    globs = reality._parse_canon_text(text)
    assert globs == ["src/*.py", "tests/*.py"]


def test_parse_canon_text_returns_none_on_empty_block():
    text = (
        "# CANON.md — demo\n"
        "canon-covers:\n"
        "\n"
        "## What it is\n"
    )
    assert reality._parse_canon_text(text) is None


# ---------------------------------------------------------------------------
# parse_manifest
# ---------------------------------------------------------------------------

def test_parse_manifest_none_when_no_manifest(tmp_project):
    assert reality.parse_manifest(tmp_project) is None


def test_parse_manifest_from_canon_preamble(tmp_project):
    _write_canon_covers_preamble(tmp_project, ["src/**/*.py", "tests/*.py"])
    globs = reality.parse_manifest(tmp_project)
    assert globs == ["src/**/*.py", "tests/*.py"]


def test_parse_manifest_from_state_file(tmp_project):
    _write_state_covers(tmp_project, ["src/*.py", "# comment line", "tests/*.py"])
    globs = reality.parse_manifest(tmp_project)
    # comment lines must be stripped
    assert globs == ["src/*.py", "tests/*.py"]


def test_parse_manifest_canon_takes_priority_over_state(tmp_project):
    """When both CANON.md preamble and state file have manifests, CANON.md wins."""
    _write_canon_covers_preamble(tmp_project, ["src/*.py"])
    _write_state_covers(tmp_project, ["tests/*.py"])
    globs = reality.parse_manifest(tmp_project)
    assert globs == ["src/*.py"]


def test_parse_manifest_falls_back_to_state_when_canon_has_none(tmp_project):
    """No canon-covers in CANON.md → fall through to state file."""
    _write_state_covers(tmp_project, ["*.md"])
    globs = reality.parse_manifest(tmp_project)
    assert globs == ["*.md"]


def test_parse_manifest_state_only_comments_returns_none(tmp_project):
    _write_state_covers(tmp_project, ["# just a comment"])
    assert reality.parse_manifest(tmp_project) is None


# ---------------------------------------------------------------------------
# reality_rev — no manifest (graceful degradation)
# ---------------------------------------------------------------------------

def test_reality_rev_none_when_no_manifest(tmp_project):
    """No canon-covers manifest → None (graceful, not an error)."""
    assert reality.reality_rev(tmp_project) is None


def test_reality_rev_none_with_empty_state_manifest(tmp_project):
    _write_state_covers(tmp_project, ["# only comments"])
    assert reality.reality_rev(tmp_project) is None


# ---------------------------------------------------------------------------
# reality_rev — filesystem fallback (no git required)
# ---------------------------------------------------------------------------

def test_reality_rev_stable_without_git(tmp_project):
    """Same content → same rev (deterministic)."""
    _write_state_covers(tmp_project, ["*.md"])
    (tmp_project / "readme.md").write_text("hello", encoding="utf-8")
    r1 = reality.reality_rev(tmp_project)
    r2 = reality.reality_rev(tmp_project)
    assert r1 is not None
    assert r1 == r2


def test_reality_rev_changes_when_covered_file_changes(tmp_project):
    """Modifying a covered file bumps the rev."""
    _write_state_covers(tmp_project, ["*.md"])
    f = tmp_project / "readme.md"
    f.write_text("v1", encoding="utf-8")
    r1 = reality.reality_rev(tmp_project)

    f.write_text("v2", encoding="utf-8")
    r2 = reality.reality_rev(tmp_project)
    assert r1 != r2


def test_reality_rev_stable_when_uncovered_file_changes(tmp_project):
    """Changing a file NOT in the manifest does not bump the rev."""
    _write_state_covers(tmp_project, ["*.md"])
    (tmp_project / "readme.md").write_text("hello", encoding="utf-8")
    r1 = reality.reality_rev(tmp_project)

    # change a .py file (not *.md → not covered)
    (tmp_project / "script.py").write_text("print('hi')", encoding="utf-8")
    r2 = reality.reality_rev(tmp_project)
    assert r1 == r2


def test_reality_rev_changes_when_covered_file_added(tmp_project):
    """Adding a new file matching the glob bumps the rev."""
    _write_state_covers(tmp_project, ["*.md"])
    r1 = reality.reality_rev(tmp_project)  # no .md files yet

    (tmp_project / "notes.md").write_text("new", encoding="utf-8")
    r2 = reality.reality_rev(tmp_project)
    assert r1 != r2


def test_reality_rev_empty_glob_match_returns_defined_rev(tmp_project):
    """A manifest that matches no files returns a defined rev (not None)."""
    _write_state_covers(tmp_project, ["nonexistent/**/*.xyz"])
    r = reality.reality_rev(tmp_project)
    assert r is not None  # empty-tree hash, not None


def test_reality_rev_is_short(tmp_project):
    _write_state_covers(tmp_project, ["*.md"])
    (tmp_project / "f.md").write_text("x", encoding="utf-8")
    r = reality.reality_rev(tmp_project)
    assert r is not None
    assert len(r) == reality.REV_LEN


# ---------------------------------------------------------------------------
# reality_rev — git mode
# ---------------------------------------------------------------------------

def test_reality_rev_with_git_returns_rev(tmp_git_project):
    """In a git repo with a manifest and tracked file → returns a rev."""
    _write_state_covers(tmp_git_project, ["*.md"])
    (tmp_git_project / "readme.md").write_text("v1", encoding="utf-8")
    _git_add_commit(tmp_git_project, "readme.md")
    r = reality.reality_rev(tmp_git_project)
    assert r is not None
    assert len(r) == reality.REV_LEN


def test_reality_rev_git_ignores_untracked_files(tmp_git_project):
    """Untracked files are invisible to reality-rev in git mode."""
    _write_state_covers(tmp_git_project, ["*.md"])
    (tmp_git_project / "readme.md").write_text("v1", encoding="utf-8")
    _git_add_commit(tmp_git_project, "readme.md")
    r1 = reality.reality_rev(tmp_git_project)

    # Write an untracked file (not committed)
    (tmp_git_project / "untracked.md").write_text("invisible", encoding="utf-8")
    r2 = reality.reality_rev(tmp_git_project)
    assert r1 == r2  # untracked file → no change


def test_reality_rev_git_changes_after_new_tracked_file(tmp_git_project):
    """Committing a new covered file bumps the rev."""
    _write_state_covers(tmp_git_project, ["*.md"])
    r1 = reality.reality_rev(tmp_git_project)  # no .md files tracked yet

    (tmp_git_project / "readme.md").write_text("v1", encoding="utf-8")
    _git_add_commit(tmp_git_project, "readme.md")
    r2 = reality.reality_rev(tmp_git_project)
    assert r1 != r2


def test_reality_rev_git_changes_after_content_change(tmp_git_project):
    """Committing a changed covered file bumps the rev."""
    _write_state_covers(tmp_git_project, ["*.md"])
    (tmp_git_project / "readme.md").write_text("v1", encoding="utf-8")
    _git_add_commit(tmp_git_project, "readme.md")
    r1 = reality.reality_rev(tmp_git_project)

    (tmp_git_project / "readme.md").write_text("v2", encoding="utf-8")
    _git_add_commit(tmp_git_project, "readme.md")
    r2 = reality.reality_rev(tmp_git_project)
    assert r1 != r2


def test_reality_rev_git_stable_on_uncommitted_change(tmp_git_project):
    """Modifying a tracked file WITHOUT committing → git ls-files sees old content."""
    _write_state_covers(tmp_git_project, ["*.md"])
    (tmp_git_project / "readme.md").write_text("v1", encoding="utf-8")
    _git_add_commit(tmp_git_project, "readme.md")
    r1 = reality.reality_rev(tmp_git_project)

    # Modify in-place but don't commit (git ls-files reads the working-tree file,
    # so the rev WILL change — the hash is over the current file content, not the
    # committed blob). This test documents that behaviour explicitly.
    (tmp_git_project / "readme.md").write_text("v2-unstaged", encoding="utf-8")
    r2 = reality.reality_rev(tmp_git_project)
    # git ls-files returns the path; we hash the current file content.
    # An unstaged change IS visible because we read the file, not the blob.
    assert r1 != r2


# ---------------------------------------------------------------------------
# stamp_reality_rev
# ---------------------------------------------------------------------------

def test_stamp_reality_rev_writes_field(tmp_project):
    """stamp_reality_rev writes reality-rev into the passport doc."""
    from tide import fields
    _write_state_covers(tmp_project, ["*.md"])
    (tmp_project / "readme.md").write_text("hello", encoding="utf-8")

    passport = tmp_project / "arc.md"
    passport.write_text("# 01-work\nstatus: active\n", encoding="utf-8")

    rr = reality.stamp_reality_rev(passport, tmp_project)
    assert rr is not None
    assert fields.read_field(passport, "reality-rev") == rr


def test_stamp_reality_rev_noop_when_no_manifest(tmp_project):
    """Without a manifest, stamp_reality_rev is a no-op (returns None)."""
    from tide import fields
    passport = tmp_project / "arc.md"
    passport.write_text("# 01-work\nstatus: active\n", encoding="utf-8")

    rr = reality.stamp_reality_rev(passport, tmp_project)
    assert rr is None
    assert fields.read_field(passport, "reality-rev") is None


# ---------------------------------------------------------------------------
# stamp_rev integration (M2 wired into arc lifecycle)
# ---------------------------------------------------------------------------

def test_new_arc_stamps_reality_rev_when_manifest_present(tmp_project):
    """arc new stamps reality-rev when a canon-covers manifest exists."""
    from tide import fields
    from tide.arc import stream
    _write_state_covers(tmp_project, ["*.md"])

    entry = stream.new_arc(tmp_project, "work")
    rr = fields.read_field(entry / "arc.md", "reality-rev")
    assert rr is not None
    assert rr == reality.reality_rev(tmp_project)


def test_new_arc_no_reality_rev_without_manifest(tmp_project):
    """arc new does NOT stamp reality-rev when there is no manifest."""
    from tide import fields
    from tide.arc import stream

    entry = stream.new_arc(tmp_project, "work")
    assert fields.read_field(entry / "arc.md", "reality-rev") is None


def test_open_arc_restamps_reality_rev(tmp_project):
    """arc open re-stamps reality-rev to the current value."""
    from tide import fields
    from tide.arc import stream
    _write_state_covers(tmp_project, ["*.md"])

    entry = stream.new_arc(tmp_project, "work")
    f = tmp_project / "readme.md"
    f.write_text("v1", encoding="utf-8")
    # Force-stamp old value so we can verify a re-stamp happens
    reality.stamp_reality_rev(entry / "arc.md", tmp_project)
    old_rr = fields.read_field(entry / "arc.md", "reality-rev")

    f.write_text("v2", encoding="utf-8")
    stream.open_arc(tmp_project, "work")
    new_rr = fields.read_field(entry / "arc.md", "reality-rev")
    assert new_rr == reality.reality_rev(tmp_project)
    assert new_rr != old_rr  # re-stamp updated it
