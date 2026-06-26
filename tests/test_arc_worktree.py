"""Tests for tide.arc.worktree — per-arc git worktree isolation (11-arc-worktree-isolation).

Coverage:
  (a) create → isolation: edit in worktree, main file unchanged
  (b) land clean: committed change in worktree lands onto base
  (c) conflict surfaces: two arcs edit the same line → land A clean, land B returns
      conflict=True and leaves repo clean (no .git/MERGE_HEAD)
  (d) non-git project: create returns None, land/remove are no-ops, no crash
  (e) close integration: arc with committed worktree change → stream.close lands it
      (change visible on base) + worktree gone
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.conftest import build_tide_skeleton, strip_placeholders
from tide import fields
from tide.arc import stream, worktree
from tide.arc.worktree import LandResult, WorktreeError


# ---------------------------------------------------------------------------
# Git repo fixture
# ---------------------------------------------------------------------------

def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _make_git_project(tmp_path: Path, name: str = "test-project") -> Path:
    """Create a tmp_path with a git repo + tide skeleton + initial commit."""
    build_tide_skeleton(tmp_path, name=name)

    _git(tmp_path, "init")
    # Configure git identity so commits work in CI and sandboxed environments.
    _git(tmp_path, "config", "user.email", "test@tide.local")
    _git(tmp_path, "config", "user.name", "Tide Test")

    # Write a seed file so we have something to commit.
    seed = tmp_path / "seed.txt"
    seed.write_text("initial content\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "initial commit")
    return tmp_path


@pytest.fixture
def git_project(tmp_path: Path) -> Path:
    """A tmp dir with a git repo and a tide skeleton, one initial commit."""
    return _make_git_project(tmp_path)


# ---------------------------------------------------------------------------
# (a) create → file isolation
# ---------------------------------------------------------------------------

class TestCreate:
    def test_create_returns_worktree_path(self, git_project):
        arc = stream.new_arc(git_project, "alpha")
        wt = worktree.create(git_project, arc)
        assert wt is not None
        assert wt.is_dir()

    def test_create_records_branch_in_passport(self, git_project):
        arc = stream.new_arc(git_project, "alpha")
        worktree.create(git_project, arc)
        branch = fields.read_field(worktree._passport(arc), worktree.BRANCH_FIELD)
        assert branch == "arc/alpha"

    def test_create_isolation_edit_does_not_touch_main(self, git_project):
        """Edit a file inside the worktree; main working tree must be unchanged."""
        arc = stream.new_arc(git_project, "alpha")
        wt = worktree.create(git_project, arc)
        assert wt is not None

        # Edit a file inside the worktree.
        isolated_file = wt / "worktree_edit.txt"
        isolated_file.write_text("only in worktree\n", encoding="utf-8")

        # The main project root must NOT have this file.
        main_file = git_project / "worktree_edit.txt"
        assert not main_file.exists(), "worktree edit leaked into main working tree"

    def test_create_twice_raises(self, git_project):
        arc = stream.new_arc(git_project, "alpha")
        worktree.create(git_project, arc)
        with pytest.raises(WorktreeError, match="worktree already exists"):
            worktree.create(git_project, arc)

    def test_create_non_git_returns_none(self, tmp_project):
        """Non-git project: create returns None (graceful fallback, no crash)."""
        arc = stream.new_arc(tmp_project, "alpha")
        result = worktree.create(tmp_project, arc)
        assert result is None

    def test_creates_gitignore_in_worktrees_dir(self, git_project):
        arc = stream.new_arc(git_project, "beta")
        worktree.create(git_project, arc)
        ig = git_project / ".tide" / "worktrees" / ".gitignore"
        assert ig.is_file()
        assert ig.read_text(encoding="utf-8").strip() == "*"


# ---------------------------------------------------------------------------
# (b) land clean — committed change reaches base
# ---------------------------------------------------------------------------

class TestLandClean:
    def test_land_merges_change_to_base(self, git_project):
        """A change committed in the worktree lands on base after land()."""
        arc = stream.new_arc(git_project, "feat")
        wt = worktree.create(git_project, arc)
        assert wt is not None

        # Commit a new file inside the worktree.
        new_file = wt / "feat.txt"
        new_file.write_text("new feature\n", encoding="utf-8")
        _git(wt, "add", "-A")
        _git(wt, "commit", "-m", "add feat.txt")

        result = worktree.land(git_project, arc)
        assert result.landed is True
        assert result.conflict is False

        # The file must now be present on base.
        assert (git_project / "feat.txt").is_file()

    def test_land_clean_removes_branch(self, git_project):
        """land() followed by remove() drops the arc branch."""
        arc = stream.new_arc(git_project, "feat")
        wt = worktree.create(git_project, arc)
        assert wt is not None
        _git(wt, "commit", "--allow-empty", "-m", "empty commit")

        result = worktree.land(git_project, arc)
        assert result.landed
        worktree.remove(git_project, arc)

        # Branch should be gone.
        branches = _git(git_project, "branch").stdout
        assert "arc/feat" not in branches

    def test_land_clears_branch_field(self, git_project):
        """After remove(), the passport branch field is cleared."""
        arc = stream.new_arc(git_project, "feat")
        worktree.create(git_project, arc)
        _git(worktree.worktree_path(git_project, arc), "commit", "--allow-empty", "-m", "x")
        worktree.land(git_project, arc)
        worktree.remove(git_project, arc)

        branch = fields.read_field(worktree._passport(arc), worktree.BRANCH_FIELD)
        assert not branch  # empty string or None


# ---------------------------------------------------------------------------
# (c) conflict surfaces and leaves repo clean
# ---------------------------------------------------------------------------

class TestConflict:
    def test_conflict_returns_conflict_true(self, git_project):
        """Two arcs editing the same line: land A clean, land B → conflict=True."""
        # Create two arcs.
        arc_a = stream.new_arc(git_project, "arc-a")
        arc_b = stream.new_arc(git_project, "arc-b")

        wt_a = worktree.create(git_project, arc_a)
        wt_b = worktree.create(git_project, arc_b)
        assert wt_a and wt_b

        # Both edit the same line in seed.txt.
        (wt_a / "seed.txt").write_text("arc-A version\n", encoding="utf-8")
        _git(wt_a, "add", "-A")
        _git(wt_a, "commit", "-m", "arc-a edit seed.txt")

        (wt_b / "seed.txt").write_text("arc-B version\n", encoding="utf-8")
        _git(wt_b, "add", "-A")
        _git(wt_b, "commit", "-m", "arc-b edit seed.txt")

        # Land A cleanly.
        result_a = worktree.land(git_project, arc_a)
        assert result_a.landed is True
        worktree.remove(git_project, arc_a)

        # Land B — must conflict.
        result_b = worktree.land(git_project, arc_b)
        assert result_b.landed is False
        assert result_b.conflict is True

    def test_conflict_leaves_repo_clean(self, git_project):
        """After a conflict land, the repo must have no lingering MERGE_HEAD."""
        arc_a = stream.new_arc(git_project, "arc-x")
        arc_b = stream.new_arc(git_project, "arc-y")

        wt_a = worktree.create(git_project, arc_a)
        wt_b = worktree.create(git_project, arc_b)

        (wt_a / "seed.txt").write_text("version-x\n", encoding="utf-8")
        _git(wt_a, "add", "-A")
        _git(wt_a, "commit", "-m", "x")

        (wt_b / "seed.txt").write_text("version-y\n", encoding="utf-8")
        _git(wt_b, "add", "-A")
        _git(wt_b, "commit", "-m", "y")

        worktree.land(git_project, arc_a)
        worktree.remove(git_project, arc_a)

        worktree.land(git_project, arc_b)

        # No lingering merge state.
        merge_head = git_project / ".git" / "MERGE_HEAD"
        assert not merge_head.exists(), ".git/MERGE_HEAD left behind after conflict"


# ---------------------------------------------------------------------------
# (d) non-git project — graceful no-ops
# ---------------------------------------------------------------------------

class TestNonGit:
    def test_is_git_repo_false_for_non_git(self, tmp_project):
        assert worktree.is_git_repo(tmp_project) is False

    def test_create_non_git_returns_none(self, tmp_project):
        arc = stream.new_arc(tmp_project, "alpha")
        assert worktree.create(tmp_project, arc) is None

    def test_land_non_git_returns_no_op(self, tmp_project):
        arc = stream.new_arc(tmp_project, "alpha")
        result = worktree.land(tmp_project, arc)
        assert result.landed is False
        assert result.conflict is False
        assert "no worktree" in result.detail

    def test_remove_non_git_returns_false(self, tmp_project):
        arc = stream.new_arc(tmp_project, "alpha")
        assert worktree.remove(tmp_project, arc) is False

    def test_has_worktree_false_for_non_git(self, tmp_project):
        arc = stream.new_arc(tmp_project, "alpha")
        assert worktree.has_worktree(tmp_project, arc) is False


# ---------------------------------------------------------------------------
# (e) close integration — stream.close lands the worktree
# ---------------------------------------------------------------------------

class TestCloseIntegration:
    def test_close_lands_worktree_change_and_removes_it(self, git_project):
        """stream.close on an arc with a committed worktree change lands the branch."""
        arc = stream.new_arc(git_project, "ship-it")
        wt = worktree.create(git_project, arc)
        assert wt is not None

        # Commit a file from the worktree.
        (wt / "output.txt").write_text("done\n", encoding="utf-8")
        _git(wt, "add", "-A")
        _git(wt, "commit", "-m", "add output.txt")

        # Populate the arc's output/ and passport so close guards pass.
        out_dir = arc / "output"
        (out_dir / "result.md").write_text("the result\n", encoding="utf-8")
        strip_placeholders(worktree._passport(arc))

        stream.close(git_project, "ship-it", force=False)

        # The output.txt committed in the worktree must now exist on base.
        assert (git_project / "output.txt").is_file()

        # The worktree directory must be gone.
        assert not worktree.worktree_path(git_project, arc).exists()

    def test_close_no_worktree_still_works(self, git_project):
        """stream.close without a worktree (plain arc) must still close normally."""
        arc = stream.new_arc(git_project, "plain")
        out_dir = arc / "output"
        (out_dir / "result.md").write_text("done\n", encoding="utf-8")
        strip_placeholders(worktree._passport(arc))

        closed = stream.close(git_project, "plain", force=False)
        assert "__" in closed.name  # renamed to __NN-plain__

    def test_close_conflict_blocks_close(self, git_project):
        """stream.close when land would conflict raises StreamError."""
        # Land arc_a to set a baseline change.
        arc_a = stream.new_arc(git_project, "arc-conflict-a")
        arc_b = stream.new_arc(git_project, "arc-conflict-b")

        wt_a = worktree.create(git_project, arc_a)
        wt_b = worktree.create(git_project, arc_b)

        (wt_a / "seed.txt").write_text("from-a\n", encoding="utf-8")
        _git(wt_a, "add", "-A")
        _git(wt_a, "commit", "-m", "a")

        (wt_b / "seed.txt").write_text("from-b\n", encoding="utf-8")
        _git(wt_b, "add", "-A")
        _git(wt_b, "commit", "-m", "b")

        # Close arc_a successfully first (lands fine).
        (arc_a / "output" / "r.md").write_text("done\n", encoding="utf-8")
        strip_placeholders(worktree._passport(arc_a))
        stream.close(git_project, "arc-conflict-a", force=False)

        # Now closing arc_b must fail because seed.txt conflicts.
        (arc_b / "output" / "r.md").write_text("done\n", encoding="utf-8")
        strip_placeholders(worktree._passport(arc_b))
        with pytest.raises(stream.StreamError, match="conflict"):
            stream.close(git_project, "arc-conflict-b", force=False)

    def test_close_force_discards_worktree_without_landing(self, git_project):
        """stream.close -f on an arc with worktree discards the worktree silently."""
        arc = stream.new_arc(git_project, "force-close")
        wt = worktree.create(git_project, arc)
        assert wt is not None
        _git(wt, "commit", "--allow-empty", "-m", "empty")

        # Use force=True (supersede path) — should not try to land.
        stream.close(git_project, "force-close", force=True)

        # The worktree must be gone.
        assert not worktree.worktree_path(git_project, arc).exists()

    def test_close_non_git_no_op_gate(self, tmp_project):
        """stream.close on a non-git project must not crash — the gate is a pure no-op."""
        arc = stream.new_arc(tmp_project, "non-git")
        out_dir = arc / "output"
        (out_dir / "result.md").write_text("done\n", encoding="utf-8")
        strip_placeholders(worktree._passport(arc))

        closed = stream.close(tmp_project, "non-git", force=False)
        assert "__" in closed.name


# ---------------------------------------------------------------------------
# has_worktree
# ---------------------------------------------------------------------------

class TestHasWorktree:
    def test_has_worktree_true_after_create(self, git_project):
        arc = stream.new_arc(git_project, "has-wt")
        worktree.create(git_project, arc)
        assert worktree.has_worktree(git_project, arc) is True

    def test_has_worktree_false_before_create(self, git_project):
        arc = stream.new_arc(git_project, "no-wt")
        assert worktree.has_worktree(git_project, arc) is False

    def test_has_worktree_false_after_remove(self, git_project):
        arc = stream.new_arc(git_project, "removed")
        worktree.create(git_project, arc)
        _git(worktree.worktree_path(git_project, arc), "commit", "--allow-empty", "-m", "x")
        worktree.land(git_project, arc)
        worktree.remove(git_project, arc)
        assert worktree.has_worktree(git_project, arc) is False


# ---------------------------------------------------------------------------
# resolve_cwd (re-entry cwd: orca-workspace > git worktree > root)
# ---------------------------------------------------------------------------

class TestResolveCwd:
    def test_resolve_cwd_none_arc_returns_root(self, tmp_project):
        assert worktree.resolve_cwd(tmp_project, None) == tmp_project

    def test_resolve_cwd_falls_back_to_root(self, tmp_project):
        arc = stream.new_arc(tmp_project, "no-wt")
        assert worktree.resolve_cwd(tmp_project, arc) == tmp_project

    def test_resolve_cwd_prefers_orca_workspace(self, tmp_project):
        from tide.adapters.orca_worktree import WORKSPACE_FIELD

        arc = stream.new_arc(tmp_project, "has-orca")
        ws = tmp_project / "orca-ws"
        ws.mkdir()
        fields.set_field(worktree._passport(arc), WORKSPACE_FIELD, str(ws))
        assert worktree.resolve_cwd(tmp_project, arc) == ws

    def test_resolve_cwd_ignores_stale_orca_workspace(self, tmp_project):
        """A recorded orca-workspace that no longer exists must fall through, not crash."""
        from tide.adapters.orca_worktree import WORKSPACE_FIELD

        arc = stream.new_arc(tmp_project, "stale-orca")
        fields.set_field(
            worktree._passport(arc), WORKSPACE_FIELD, str(tmp_project / "gone")
        )
        assert worktree.resolve_cwd(tmp_project, arc) == tmp_project

    def test_resolve_cwd_falls_back_to_git_worktree(self, git_project):
        arc = stream.new_arc(git_project, "wt-arc")
        wt = worktree.create(git_project, arc)
        assert wt is not None and wt.exists()
        assert worktree.resolve_cwd(git_project, arc) == wt

    def test_resolve_cwd_orca_workspace_beats_git_worktree(self, git_project):
        from tide.adapters.orca_worktree import WORKSPACE_FIELD

        arc = stream.new_arc(git_project, "both")
        worktree.create(git_project, arc)  # makes a real git worktree
        ws = git_project / "orca-ws"
        ws.mkdir()
        fields.set_field(worktree._passport(arc), WORKSPACE_FIELD, str(ws))
        assert worktree.resolve_cwd(git_project, arc) == ws


# ---------------------------------------------------------------------------
# resolve_project_and_arc (cross-project: cwd-project first, then roster)
# ---------------------------------------------------------------------------

class TestResolveProjectAndArc:
    def test_resolves_arc_in_same_project(self, tmp_project):
        arc = stream.new_arc(tmp_project, "local")
        owner, entry = worktree.resolve_project_and_arc(tmp_project, "local")
        assert owner == tmp_project
        assert entry == arc

    def test_no_match_returns_root_and_none(self, tmp_project):
        owner, entry = worktree.resolve_project_and_arc(tmp_project, "ghost")
        assert owner == tmp_project
        assert entry is None

    def test_resolves_arc_in_roster_project(self, tmp_control_home, tmp_path):
        from tide import roster
        from tests.conftest import build_tide_skeleton

        # A separate registered project that owns the arc.
        proj = tmp_path / "other-proj"
        proj.mkdir()
        build_tide_skeleton(proj, name="other")
        arc = stream.new_arc(proj, "remote-arc")
        roster.add(tmp_control_home, "other", str(proj))

        owner, entry = worktree.resolve_project_and_arc(tmp_control_home, "remote-arc")
        assert owner == proj
        assert entry == arc

    def test_does_not_walk_roster_from_plain_project(self, tmp_project, tmp_path):
        # A plain project (no roster.md) never reaches into other projects.
        proj = tmp_path / "elsewhere"
        proj.mkdir()
        from tests.conftest import build_tide_skeleton

        build_tide_skeleton(proj, name="elsewhere")
        stream.new_arc(proj, "remote-arc")
        owner, entry = worktree.resolve_project_and_arc(tmp_project, "remote-arc")
        assert owner == tmp_project
        assert entry is None
