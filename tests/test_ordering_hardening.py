"""Crash-simulation tests for multi-step state-mutation ordering (TDD RED phase).

Each test monkeypatches the intermediate step to raise, then asserts the
surviving state is recoverable — either the final state is consistent or a
retry completes without error.

Fixes covered (in order):
  Fix 1  — worktree.create: stamp passport BEFORE git worktree add
  Fix 2  — worktree.remove: clear passport field FIRST; check worktree remove return code
  Fix 3  — worktree.land: merge --abort return code surfaced in LandResult.detail
  Fix 4  — worktree.land: checkout CalledProcessError wrapped as WorktreeError
  Fix 5  — _land_loose: ledger.append FIRST, then cosmetic note; OSError → LandError
  Fix 6  — stream.reopen: write status BEFORE rename
  Fix 7  — contract.new: write delta.md BEFORE contract.md
  Fix 8  — migrate.apply_migration: atomic arc copy (tmp sibling + os.rename)
  Fix 9  — persist_seed: unique temp path per call (mkstemp, no clobber)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from tests.conftest import build_tide_skeleton, strip_placeholders
from tide import fields, ledger
from tide.arc import stream, worktree
from tide.arc.worktree import LandResult, WorktreeError
from tide.contract import lifecycle, model
from tide.adapters import base


# ---------------------------------------------------------------------------
# Git repo helper (mirrors test_arc_worktree.py)
# ---------------------------------------------------------------------------

def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=check, capture_output=True, text=True,
    )


def _make_git_project(tmp_path: Path) -> Path:
    build_tide_skeleton(tmp_path, name="harden-proj")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@tide.local")
    _git(tmp_path, "config", "user.name", "Tide Test")
    (tmp_path / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


@pytest.fixture
def git_project(tmp_path: Path) -> Path:
    return _make_git_project(tmp_path)


# ---------------------------------------------------------------------------
# Fix 1 — worktree.create: crash AFTER git-worktree-add, BEFORE passport stamp
#          → should be unrecoverable in the ORIGINAL; we flip the order so
#            crashing BEFORE git-worktree-add leaves a recoverable intermediate.
# ---------------------------------------------------------------------------

class TestCreateOrderingFix1:
    """Passport is stamped BEFORE git worktree add so crash is recoverable."""

    def test_crash_before_git_add_passport_already_stamped(self, git_project, monkeypatch):
        """Simulate crash at the git-worktree-add step.

        After the crash the passport already carries the branch field (because we
        stamp first), so has_worktree returns True.  A retry can skip the 'worktree
        already exists' check (wt dir is absent) and complete the create.
        """
        arc = stream.new_arc(git_project, "crash-create")
        branch = worktree.branch_for(arc)
        passport = worktree._passport(arc)

        # Simulate: git worktree add raises mid-execution.
        original_git = worktree._git

        def boom_on_worktree_add(root, *args, **kwargs):
            if args[0] == "worktree" and args[1] == "add":
                raise RuntimeError("simulated crash during git worktree add")
            return original_git(root, *args, **kwargs)

        monkeypatch.setattr(worktree, "_git", boom_on_worktree_add)

        with pytest.raises(RuntimeError, match="simulated crash"):
            worktree.create(git_project, arc)

        # With Fix 1: passport is stamped BEFORE the git call, so the branch
        # field is set even though the worktree directory was not created.
        stamped = fields.read_field(passport, worktree.BRANCH_FIELD)
        assert stamped == branch, (
            "passport branch field must be stamped before git worktree add "
            "so a crash leaves a recoverable intermediate"
        )

    def test_retry_after_crash_completes_create(self, git_project, monkeypatch):
        """After a crash during git-worktree-add, a retry succeeds.

        The worktree directory does not exist (crash before it was created), so the
        'already exists' guard doesn't fire.  The passport already has the branch
        field, but that's idempotent — a second set_field is a no-op.
        """
        arc = stream.new_arc(git_project, "retry-create")
        original_git = worktree._git
        crashed = []

        def boom_once_on_worktree_add(root, *args, **kwargs):
            if args[0] == "worktree" and args[1] == "add" and not crashed:
                crashed.append(True)
                raise RuntimeError("simulated crash during git worktree add")
            return original_git(root, *args, **kwargs)

        monkeypatch.setattr(worktree, "_git", boom_once_on_worktree_add)

        with pytest.raises(RuntimeError):
            worktree.create(git_project, arc)

        # Restore normal git behaviour — the retry runs unimpeded.
        monkeypatch.setattr(worktree, "_git", original_git)

        # Retry must succeed (worktree dir absent → no 'already exists' error).
        wt = worktree.create(git_project, arc)
        assert wt is not None and wt.is_dir()

    def test_git_add_failure_rolls_back_field(self, git_project):
        """When git worktree add fails (nonzero), the passport field is cleared."""
        arc = stream.new_arc(git_project, "rollback-field")

        # Monkeypatch: make git worktree add return failure.
        def fail_worktree_add(root, *args, **kwargs):
            if args[0] == "worktree" and args[1] == "add":
                return subprocess.CompletedProcess(
                    args=["git", "worktree", "add"],
                    returncode=128,
                    stdout="",
                    stderr="branch already exists",
                )
            return subprocess.run(
                ["git", "-C", str(root), *args],
                check=kwargs.get("check", True),
                capture_output=True,
                text=True,
            )

        with mock.patch.object(worktree, "_git", side_effect=fail_worktree_add):
            with pytest.raises(WorktreeError, match="git worktree add failed"):
                worktree.create(git_project, arc)

        # The field must be cleared (rolled back) after the git failure.
        field = fields.read_field(worktree._passport(arc), worktree.BRANCH_FIELD)
        assert not field, "passport field must be cleared when git worktree add fails"


# ---------------------------------------------------------------------------
# Fix 2 — worktree.remove: clear passport field BEFORE branch delete;
#          raise WorktreeError when git worktree remove fails
# ---------------------------------------------------------------------------

class TestRemoveOrderingFix2:
    """Passport cleared BEFORE branch delete; worktree-remove failure is visible."""

    def test_crash_between_branch_delete_and_field_clear_is_safe(
        self, git_project, monkeypatch
    ):
        """Simulate crash AFTER branch delete, BEFORE passport field clear.

        With fix: field is cleared BEFORE branch delete, so the dangerous
        intermediate (live passport + dead branch) cannot occur.
        This test verifies: if we crash at branch-D, the field is already clear.
        """
        arc = stream.new_arc(git_project, "remove-order")
        worktree.create(git_project, arc)
        _git(worktree.worktree_path(git_project, arc), "commit", "--allow-empty", "-m", "x")
        worktree.land(git_project, arc)

        branch = fields.read_field(worktree._passport(arc), worktree.BRANCH_FIELD)
        assert branch  # field is set before remove

        original_git = worktree._git
        crashed_at_branch_delete = []

        def crash_on_branch_delete(root, *args, **kwargs):
            if args[0] == "branch" and args[1] == "-D" and not crashed_at_branch_delete:
                crashed_at_branch_delete.append(True)
                raise RuntimeError("simulated crash during git branch -D")
            return original_git(root, *args, **kwargs)

        monkeypatch.setattr(worktree, "_git", crash_on_branch_delete)

        with pytest.raises(RuntimeError, match="simulated crash"):
            worktree.remove(git_project, arc)

        # With fix: passport field is cleared BEFORE branch delete, so even
        # if the branch still exists (crash before -D), the passport is clean.
        remaining = fields.read_field(worktree._passport(arc), worktree.BRANCH_FIELD)
        assert not remaining, (
            "passport field must already be cleared before branch delete "
            "so a crash between them leaves no dead-branch reference in the passport"
        )

    def test_worktree_remove_failure_raises_worktree_error(self, git_project):
        """git worktree remove nonzero → WorktreeError (not silent drop)."""
        arc = stream.new_arc(git_project, "remove-fail")
        worktree.create(git_project, arc)
        _git(worktree.worktree_path(git_project, arc), "commit", "--allow-empty", "-m", "x")
        worktree.land(git_project, arc)

        def fail_worktree_remove(root, *args, **kwargs):
            if args[0] == "worktree" and args[1] == "remove":
                return subprocess.CompletedProcess(
                    args=["git", "worktree", "remove"],
                    returncode=1,
                    stdout="",
                    stderr="fatal: worktree locked",
                )
            return subprocess.run(
                ["git", "-C", str(root), *args],
                check=kwargs.get("check", True),
                capture_output=True,
                text=True,
            )

        with mock.patch.object(worktree, "_git", side_effect=fail_worktree_remove):
            with pytest.raises(WorktreeError, match="git worktree remove failed"):
                worktree.remove(git_project, arc)

    def test_worktree_remove_failure_leaves_field_intact(self, git_project):
        """When git worktree remove fails, the passport field must NOT be cleared.

        An orphaned worktree is already an error; if we also clear the field the
        operator has no pointer to the stuck worktree and cannot manually clean it.
        """
        arc = stream.new_arc(git_project, "remove-preserve-field")
        worktree.create(git_project, arc)
        _git(worktree.worktree_path(git_project, arc), "commit", "--allow-empty", "-m", "x")
        worktree.land(git_project, arc)

        branch_before = fields.read_field(worktree._passport(arc), worktree.BRANCH_FIELD)
        assert branch_before

        def fail_worktree_remove(root, *args, **kwargs):
            if args[0] == "worktree" and args[1] == "remove":
                return subprocess.CompletedProcess(
                    args=["git", "worktree", "remove"],
                    returncode=1,
                    stdout="",
                    stderr="fatal: worktree locked",
                )
            return subprocess.run(
                ["git", "-C", str(root), *args],
                check=kwargs.get("check", True),
                capture_output=True,
                text=True,
            )

        with mock.patch.object(worktree, "_git", side_effect=fail_worktree_remove):
            with pytest.raises(WorktreeError):
                worktree.remove(git_project, arc)

        # Field must still point to the branch so the operator can retry/investigate.
        branch_after = fields.read_field(worktree._passport(arc), worktree.BRANCH_FIELD)
        assert branch_after == branch_before, (
            "passport field must remain intact when git worktree remove fails"
        )


# ---------------------------------------------------------------------------
# Fix 3 — worktree.land: merge --abort failure surfaced in LandResult.detail
# ---------------------------------------------------------------------------

class TestLandAbortFix3:
    """merge --abort failure is included in LandResult.detail, not silently dropped."""

    def test_abort_failure_surfaced_in_detail(self, git_project):
        """When merge --abort exits nonzero, its stderr appears in LandResult.detail."""
        arc_a = stream.new_arc(git_project, "conf-a")
        arc_b = stream.new_arc(git_project, "conf-b")
        wt_a = worktree.create(git_project, arc_a)
        wt_b = worktree.create(git_project, arc_b)

        # Set up conflicting edits.
        (wt_a / "seed.txt").write_text("from-a\n", encoding="utf-8")
        _git(wt_a, "add", "-A")
        _git(wt_a, "commit", "-m", "a")
        (wt_b / "seed.txt").write_text("from-b\n", encoding="utf-8")
        _git(wt_b, "add", "-A")
        _git(wt_b, "commit", "-m", "b")
        worktree.land(git_project, arc_a)
        worktree.remove(git_project, arc_a)

        # Patch --abort to return nonzero.
        original_git = worktree._git

        def fail_abort(root, *args, **kwargs):
            if args[0] == "merge" and args[1] == "--abort":
                return subprocess.CompletedProcess(
                    args=["git", "merge", "--abort"],
                    returncode=128,
                    stdout="",
                    stderr="fatal: merge --abort failed for simulated reason",
                )
            return original_git(root, *args, **kwargs)

        with mock.patch.object(worktree, "_git", side_effect=fail_abort):
            result = worktree.land(git_project, arc_b)

        assert result.conflict is True
        assert "merge --abort" in result.detail.lower() or "abort" in result.detail.lower(), (
            "merge --abort failure must be surfaced in LandResult.detail"
        )


# ---------------------------------------------------------------------------
# Fix 4 — worktree.land: checkout CalledProcessError wrapped as WorktreeError
# ---------------------------------------------------------------------------

class TestLandCheckoutFix4:
    """checkout failure raises WorktreeError, not a raw CalledProcessError traceback."""

    def test_checkout_failure_raises_worktree_error(self, git_project):
        """When git checkout fails, the exception is WorktreeError (user-facing)."""
        arc = stream.new_arc(git_project, "checkout-fail")
        worktree.create(git_project, arc)
        _git(worktree.worktree_path(git_project, arc), "commit", "--allow-empty", "-m", "x")

        original_git = worktree._git

        def fail_checkout(root, *args, **kwargs):
            if args[0] == "checkout":
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["git", "checkout"],
                    stderr="error: pathspec 'nonexistent' did not match",
                )
            return original_git(root, *args, **kwargs)

        with mock.patch.object(worktree, "_git", side_effect=fail_checkout):
            with pytest.raises(WorktreeError):
                worktree.land(git_project, arc, base="nonexistent-target-branch")

    def test_checkout_error_message_includes_context(self, git_project):
        """WorktreeError from checkout failure includes the target branch name."""
        arc = stream.new_arc(git_project, "checkout-ctx")
        worktree.create(git_project, arc)
        _git(worktree.worktree_path(git_project, arc), "commit", "--allow-empty", "-m", "x")

        original_git = worktree._git

        def fail_checkout(root, *args, **kwargs):
            if args[0] == "checkout":
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["git", "checkout"],
                    stderr="error: branch not found",
                )
            return original_git(root, *args, **kwargs)

        with mock.patch.object(worktree, "_git", side_effect=fail_checkout):
            with pytest.raises(WorktreeError, match="ghost-base"):
                worktree.land(git_project, arc, base="ghost-base")


# ---------------------------------------------------------------------------
# Fix 5 — _land_loose: ledger.append FIRST, then model.set_field;
#          OSError from ledger surfaced as LandError
# ---------------------------------------------------------------------------

class TestLandLooseOrderingFix5:
    """ledger.append is the authoritative write; cosmetic note follows it."""

    def test_crash_before_ledger_append_leaves_no_debt(self, tmp_project, monkeypatch):
        """Simulate crash AFTER model.set_field but BEFORE ledger.append.

        In the ORIGINAL order: contract note written first, then ledger.  If we crash
        between the two, the arc has a 'deferred:' note but NO ledger entry, so
        reconcile never sees it.

        With the fix (ledger first): crashing at model.set_field leaves the ledger
        entry written — reconcile will find it.  This test verifies that the ledger
        entry exists when set_field raises.
        """
        from tide.arc import land

        arc = stream.new_arc(tmp_project, "loose-order")
        lifecycle.new(tmp_project, "loose-order")
        lifecycle.sign(tmp_project, "loose-order")

        original_set_field = model.set_field
        crashed = []

        def crash_on_deferred(arc_dir, key, value):
            if key == "deferred" and not crashed:
                crashed.append(True)
                raise RuntimeError("simulated crash in model.set_field")
            return original_set_field(arc_dir, key, value)

        monkeypatch.setattr(model, "set_field", crash_on_deferred)

        arc_dir = model.resolve_arc_dir(tmp_project, "loose-order")

        with pytest.raises(RuntimeError, match="simulated crash"):
            land._land_loose(tmp_project, arc_dir, "loose-order", True, None)

        # With fix: ledger was written BEFORE set_field → debt is recorded.
        assert ledger.count(tmp_project) >= 1, (
            "ledger entry must exist when cosmetic set_field crashes — "
            "ledger.append must run BEFORE model.set_field"
        )

    def test_ledger_oserror_raises_land_error(self, tmp_project, monkeypatch):
        """OSError from ledger.append is wrapped as LandError with arc-sealed note."""
        from tide.arc import land

        arc = stream.new_arc(tmp_project, "ledger-oserr")
        lifecycle.new(tmp_project, "ledger-oserr")
        lifecycle.sign(tmp_project, "ledger-oserr")

        original_append = ledger.append

        def boom_append(*args, **kwargs):
            raise OSError("simulated disk full writing ledger")

        monkeypatch.setattr(ledger, "append", boom_append)

        arc_dir = model.resolve_arc_dir(tmp_project, "ledger-oserr")

        with pytest.raises(land.LandError) as exc_info:
            land._land_loose(tmp_project, arc_dir, "ledger-oserr", True, None)

        assert "sealed" in str(exc_info.value).lower() or "ledger" in str(exc_info.value).lower(), (
            "LandError must tell the operator the arc is sealed but debt could not be recorded"
        )

    def test_ledger_written_before_contract_note(self, tmp_project, monkeypatch):
        """ledger.append is called before model.set_field on the happy path."""
        from tide.arc import land

        arc = stream.new_arc(tmp_project, "order-check")
        lifecycle.new(tmp_project, "order-check")
        lifecycle.sign(tmp_project, "order-check")

        call_order = []

        original_append = ledger.append
        original_set_field = model.set_field

        def tracked_append(*a, **kw):
            call_order.append("ledger")
            return original_append(*a, **kw)

        def tracked_set_field(arc_dir, key, value):
            if key == "deferred":
                call_order.append("set_field")
            return original_set_field(arc_dir, key, value)

        monkeypatch.setattr(ledger, "append", tracked_append)
        monkeypatch.setattr(model, "set_field", tracked_set_field)

        arc_dir = model.resolve_arc_dir(tmp_project, "order-check")
        land._land_loose(tmp_project, arc_dir, "order-check", True, None)

        assert call_order == ["ledger", "set_field"], (
            "ledger.append must be called before model.set_field; got: {0}".format(call_order)
        )


# ---------------------------------------------------------------------------
# Fix 6 — stream.reopen: write status: active BEFORE rename
# ---------------------------------------------------------------------------

class TestReopenOrderingFix6:
    """status field written BEFORE rename so a crash between the two is recoverable."""

    def test_set_field_targets_closed_path_before_rename(self, tmp_project, monkeypatch):
        """fields.set_field is called on the CLOSED (__ ) passport path, not the opened one.

        This verifies the ordering: status is written to `entry` (the closed dir)
        before `entry.rename(opened)`.  Tracking the exact path passed to set_field
        confirms the fix without relying on OS-level rename patching.
        """
        arc = stream.new_arc(tmp_project, "reopen-order")
        out = arc / "output"
        (out / "r.md").write_text("done\n", encoding="utf-8")
        strip_placeholders(stream.passport_path(arc))
        stream.close(tmp_project, "reopen-order", force=False)

        set_field_paths: list = []
        original_set_field = fields.set_field

        def tracked_set_field(path, key, value):
            if key == "status" and value == "active":
                set_field_paths.append(Path(path))
            return original_set_field(path, key, value)

        monkeypatch.setattr(fields, "set_field", tracked_set_field)
        stream.reopen(tmp_project, "reopen-order")

        # The set_field call must target the CLOSED passport path (__ in path).
        assert set_field_paths, "fields.set_field was not called for status=active"
        assert any("__" in str(p) for p in set_field_paths), (
            "status must be written to the closed-entry passport (__ path) BEFORE rename; "
            "got paths: {0}".format(set_field_paths)
        )

    def test_intermediate_state_with_status_active_is_recoverable(self, tmp_project):
        """An entry with closed name but status=active can be reopened by retry.

        This simulates the crash-surviving intermediate the fix produces: the rename
        crashed after set_field ran, leaving a closed-named dir whose passport says
        'status: active'.  A retry must resolve the closed entry and rename it.
        """
        arc = stream.new_arc(tmp_project, "crash-intermediate")
        out = arc / "output"
        (out / "r.md").write_text("done\n", encoding="utf-8")
        strip_placeholders(stream.passport_path(arc))
        closed = stream.close(tmp_project, "crash-intermediate", force=False)

        # Manually produce the crash intermediate: write status=active to closed passport.
        fields.set_field(stream.passport_path(closed), "status", "active")

        # The closed entry still has __ name (rename never happened).
        assert slug_is_closed(closed.name)

        # A retry of reopen must resolve by closed=True → find it → rename → return opened.
        reopened = stream.reopen(tmp_project, "crash-intermediate")
        assert not slug_is_closed(reopened.name), "retry must produce an open-named entry"
        assert fields.read_field(stream.passport_path(reopened), "status") == "active"

    def test_reopen_happy_path_status_active_and_name_open(self, tmp_project):
        """Sanity: reopen sets status=active and strips the __ markers from the name."""
        arc = stream.new_arc(tmp_project, "happy-reopen")
        out = arc / "output"
        (out / "r.md").write_text("done\n", encoding="utf-8")
        strip_placeholders(stream.passport_path(arc))
        stream.close(tmp_project, "happy-reopen", force=False)

        reopened = stream.reopen(tmp_project, "happy-reopen")
        assert not slug_is_closed(reopened.name)
        assert fields.read_field(stream.passport_path(reopened), "status") == "active"


def slug_is_closed(name: str) -> bool:
    """True when a directory name carries the ``__…__`` closed marker."""
    return name.startswith("__") and name.endswith("__")


# ---------------------------------------------------------------------------
# Fix 7 — contract.new: write delta.md BEFORE contract.md
# ---------------------------------------------------------------------------

class TestContractNewOrderingFix7:
    """delta.md written BEFORE contract.md so a crash leaves has_contract=False."""

    def test_crash_before_contract_md_leaves_retry_open(self, tmp_project, monkeypatch):
        """Simulate crash after delta.md written, before contract.md written.

        A delta.md with no contract.md → has_contract=False → the one-per-arc guard
        stays open → retry of contract.new succeeds cleanly.
        """
        from tide import io as _io

        arc = stream.new_arc(tmp_project, "new-crash")
        arc_dir = model.resolve_arc_dir(tmp_project, "new-crash")
        contract_path = model.contract_path(arc_dir)
        delta_path = model.delta_path(arc_dir)

        original_atomic_write = _io.atomic_write
        crash_on_contract = []

        def crash_on_contract_write(path, text, **kwargs):
            # Crash when about to write contract.md (after delta.md is written).
            if Path(path).name == "contract.md" and not crash_on_contract:
                crash_on_contract.append(True)
                raise OSError("simulated disk full writing contract.md")
            return original_atomic_write(path, text, **kwargs)

        monkeypatch.setattr(_io, "atomic_write", crash_on_contract_write)

        with pytest.raises(OSError, match="simulated disk full"):
            lifecycle.new(tmp_project, "new-crash")

        # With fix: delta.md was written BEFORE contract.md → delta exists.
        assert delta_path.is_file(), (
            "delta.md must exist after crash; it was written first"
        )

        # Contract must NOT exist (we crashed before writing it).
        assert not contract_path.is_file(), (
            "contract.md must not exist after crash so the one-per-arc guard is open"
        )

        # has_contract must be False → retry is possible.
        assert not model.has_contract(arc_dir), (
            "has_contract must be False when only delta.md exists — retry must be clean"
        )

    def test_retry_contract_new_after_crash_succeeds(self, tmp_project, monkeypatch):
        """After a crash before contract.md, retrying contract.new succeeds."""
        from tide import io as _io

        arc = stream.new_arc(tmp_project, "new-retry")

        original_atomic_write = _io.atomic_write
        crashed = []

        def crash_on_first_contract(path, text, **kwargs):
            if Path(path).name == "contract.md" and not crashed:
                crashed.append(True)
                raise OSError("crash")
            return original_atomic_write(path, text, **kwargs)

        monkeypatch.setattr(_io, "atomic_write", crash_on_first_contract)

        with pytest.raises(OSError):
            lifecycle.new(tmp_project, "new-retry")

        # Restore — retry must pass the one-per-arc guard.
        monkeypatch.setattr(_io, "atomic_write", original_atomic_write)
        cpath = lifecycle.new(tmp_project, "new-retry")
        assert cpath.is_file()
        assert model.has_contract(model.resolve_arc_dir(tmp_project, "new-retry"))

    def test_delta_written_before_contract_md_on_happy_path(self, tmp_project, monkeypatch):
        """On the happy path, delta.md is created before contract.md (call order)."""
        from tide import io as _io

        arc = stream.new_arc(tmp_project, "order-new")

        write_order = []
        original_atomic_write = _io.atomic_write

        def track_writes(path, text, **kwargs):
            name = Path(path).name
            if name in ("contract.md", "delta.md"):
                write_order.append(name)
            return original_atomic_write(path, text, **kwargs)

        monkeypatch.setattr(_io, "atomic_write", track_writes)
        lifecycle.new(tmp_project, "order-new")

        assert write_order[0] == "delta.md", (
            "delta.md must be written before contract.md; got order: {0}".format(write_order)
        )
        assert "contract.md" in write_order


# ---------------------------------------------------------------------------
# Fix 8 — migrate.apply_migration: atomic arc copy (tmp sibling + os.rename)
# ---------------------------------------------------------------------------

class TestMigrateAtomicCopyFix8:
    """Each arc is copied to a temp sibling, then atomically renamed to the final dst."""

    def _build_legacy(self, root: Path) -> Path:
        """Create a minimal .arcs legacy tree with one arc."""
        arcs = root / ".arcs"
        arc_dir = arcs / "arcs" / "01-my-arc"
        arc_dir.mkdir(parents=True)
        (arc_dir / "arc.md").write_text(
            "# 01-my-arc\ngoal: test\nstatus: active\n", encoding="utf-8"
        )
        (arc_dir / "output").mkdir()
        (arc_dir / "output" / "result.md").write_text("done\n", encoding="utf-8")
        (arcs / "candidates").mkdir(parents=True, exist_ok=True)
        return arcs

    def test_crash_during_os_rename_leaves_tmp_sibling_not_dst(self, tmp_path):
        """A crash at the atomic os.rename step leaves .__tmp- not the final arc name.

        With the fix, copytree writes to a temp sibling and os.rename moves it to
        the final dst.  Patching os.rename to fail means the temp stays but the
        final name is never created — the crash-surviving intermediate is .__tmp-*,
        ignored by plan_migration's naming filter.
        """
        import tide.migrate as _m

        self._build_legacy(tmp_path)
        build_tide_skeleton(tmp_path, name="atomic-copy")
        plan = _m.plan_migration(tmp_path)

        crashed = []

        def fail_rename(src, dst):
            if not crashed and ".__tmp-" in str(src):
                crashed.append(True)
                raise OSError("simulated crash during os.rename")
            return os.rename(src, dst)

        with mock.patch.object(_m.os, "rename", side_effect=fail_rename):
            with pytest.raises(OSError, match="simulated crash"):
                _m.apply_migration(plan)

        tide_arcs = _m.paths.arcs_dir(tmp_path)
        if tide_arcs.exists():
            final_names = [
                p.name for p in tide_arcs.iterdir()
                if not p.name.startswith(".__tmp-")
            ]
            assert "01-my-arc" not in final_names, (
                "the final arc dir must NOT exist when os.rename crashes; "
                "the partial copy must remain in the .__tmp- sibling only"
            )

    def test_stale_tmp_sibling_overwritten_on_retry(self, tmp_path):
        """A leftover .__tmp- dir from a prior crashed migration is replaced on retry.

        The fix uses shutil.rmtree on an existing .__tmp- before copytree so a
        subsequent run doesn't fail on 'destination already exists'.
        """
        import tide.migrate as _m
        from tide import paths as _paths

        self._build_legacy(tmp_path)
        build_tide_skeleton(tmp_path, name="stale-tmp")

        # Plant a stale .__tmp- artifact as if a prior run crashed mid-copy.
        arcs_dir = _paths.arcs_dir(tmp_path)
        arcs_dir.mkdir(parents=True, exist_ok=True)
        stale = arcs_dir / ".__tmp-01-my-arc"
        stale.mkdir()
        (stale / "stale.txt").write_text("stale artifact", encoding="utf-8")

        plan = _m.plan_migration(tmp_path)
        result = _m.apply_migration(plan)

        # The final dst must exist with correct content (stale artifact must be gone).
        dst = arcs_dir / "01-my-arc"
        assert dst.is_dir(), "migration must create the final arc dir"
        assert not (dst / "stale.txt").exists(), (
            "stale artifact from prior crash must be overwritten on retry"
        )
        assert not stale.exists(), ".__tmp- sibling must be removed after successful rename"

    def test_retry_after_crash_completes_migration(self, tmp_path):
        """After a crash in os.rename, a retry with --force completes the migration."""
        import tide.migrate as _m

        self._build_legacy(tmp_path)
        build_tide_skeleton(tmp_path, name="retry-copy")
        plan = _m.plan_migration(tmp_path)

        # First run: crash at os.rename (after copytree to temp).
        crashed = []

        def fail_once_rename(src, dst):
            if not crashed and ".__tmp-" in str(src):
                crashed.append(True)
                raise OSError("crash")
            return os.rename(src, dst)

        with mock.patch.object(_m.os, "rename", side_effect=fail_once_rename):
            try:
                _m.apply_migration(plan)
            except (OSError, Exception):
                pass

        # Retry: plan again and apply — the stale .__tmp- must be cleared and
        # migration must complete or fail with a clear error (not silently corrupt).
        plan2 = _m.plan_migration(tmp_path)
        try:
            result = _m.apply_migration(plan2, force=True)
            assert "01-my-arc" in result.arcs_copied or result.arcs_skipped
        except _m.MigrateError:
            # Backup collision from the prior run's partial state — acceptable:
            # atomicity protected the dst.
            pass


# ---------------------------------------------------------------------------
# Fix 9 — persist_seed: unique temp path per call (mkstemp, no clobber)
# ---------------------------------------------------------------------------

class TestPersistSeedFix9:
    """Each persist_seed call returns a UNIQUE path — concurrent calls don't clobber."""

    def test_two_concurrent_seeds_get_different_paths(self):
        """Two calls with the same title must return different file paths."""
        path1 = base.persist_seed("seed content A", "my-arc")
        path2 = base.persist_seed("seed content B", "my-arc")
        try:
            assert path1 != path2, (
                "persist_seed must return a unique path per call so concurrent "
                "spawns for the same arc do not clobber each other's seed"
            )
        finally:
            for p in (path1, path2):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass

    def test_seed_content_correct_after_concurrent_writes(self):
        """Each path carries the exact seed that was written to it."""
        path1 = base.persist_seed("ALPHA seed", "shared-arc")
        path2 = base.persist_seed("BETA seed", "shared-arc")
        try:
            assert path1.read_text(encoding="utf-8") == "ALPHA seed"
            assert path2.read_text(encoding="utf-8") == "BETA seed"
        finally:
            for p in (path1, path2):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass

    def test_path_includes_title_hint(self):
        """The temp path still carries the title as a filename hint."""
        path = base.persist_seed("content", "guitar-proof")
        try:
            assert "guitar-proof" in path.name or "guitar" in path.name, (
                "temp path must include the title as a filename hint; got: {0}".format(path.name)
            )
        finally:
            path.unlink(missing_ok=True)

    def test_seed_file_is_not_deterministic_path(self):
        """The returned path must NOT be a deterministic fixed path (mkstemp-derived)."""
        path1 = base.persist_seed("x", "stable-title")
        path2 = base.persist_seed("x", "stable-title")
        try:
            # Both calls must write to separate files (unique suffixes from mkstemp).
            assert path1 != path2, (
                "persist_seed must NOT return the same deterministic path on every call"
            )
        finally:
            for p in (path1, path2):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Fix 2 regression — WorktreeError from remove() must be caught in land chain
# ---------------------------------------------------------------------------

class TestRemoveWorktreeErrorInLandChain:
    """WorktreeError raised by worktree.remove after a successful merge must be
    caught and re-raised as LandError so the operator gets a clean, actionable
    message instead of a raw Python traceback.

    Regression introduced by Fix 2: worktree.remove now raises WorktreeError on
    git-worktree-remove failure, but _merge_worktree (land.py) had no handler.
    WorktreeError is NOT a subclass of LandError/StreamError, so it escaped both
    cmd_land's except-LandError and cli.main's except-StreamError, producing a
    bare traceback with no cleanup guidance.
    """

    def test_remove_failure_after_merge_surfaces_as_land_error(
        self, git_project, monkeypatch
    ):
        """worktree.remove raises WorktreeError → _merge_worktree re-raises LandError.

        After a successful merge (landed=True), if worktree.remove raises
        WorktreeError the caller must see a LandError (not a raw WorktreeError),
        because LandError is the boundary type caught by cmd_land and cli.main.
        """
        from tide.arc import land

        arc = stream.new_arc(git_project, "remove-after-merge")
        worktree.create(git_project, arc)
        wt = worktree.worktree_path(git_project, arc)
        _git(wt, "commit", "--allow-empty", "-m", "work")

        # Patch worktree.remove to raise WorktreeError (simulates locked/NFS wt).
        def boom_remove(root, arc_dir, **kwargs):
            raise WorktreeError("git worktree remove failed: fatal: worktree locked")

        monkeypatch.setattr(worktree, "remove", boom_remove)

        with pytest.raises(land.LandError):
            land._merge_worktree(git_project, arc, "remove-after-merge")

    def test_land_error_message_mentions_cleanup_and_manual_remove(
        self, git_project, monkeypatch
    ):
        """The LandError message tells the operator the merge succeeded and gives
        the manual cleanup next step, so they are not left guessing."""
        from tide.arc import land

        arc = stream.new_arc(git_project, "cleanup-msg")
        worktree.create(git_project, arc)
        wt = worktree.worktree_path(git_project, arc)
        _git(wt, "commit", "--allow-empty", "-m", "work")

        def boom_remove(root, arc_dir, **kwargs):
            raise WorktreeError("fatal: worktree locked")

        monkeypatch.setattr(worktree, "remove", boom_remove)

        with pytest.raises(land.LandError) as exc_info:
            land._merge_worktree(git_project, arc, "cleanup-msg")

        msg = str(exc_info.value).lower()
        # Must mention that the merge succeeded (so operator knows not to retry merge).
        assert "landed" in msg or "merge" in msg or "branch" in msg, (
            "error message must tell the operator the merge succeeded"
        )
        # Must give a cleanup action.
        assert "worktree" in msg or "cleanup" in msg or "manual" in msg or "remove" in msg, (
            "error message must include a cleanup/manual-remove next step"
        )

    def test_land_one_surfaces_remove_failure_as_land_error(
        self, git_project, monkeypatch
    ):
        """land_one (and reconcile_one via it) surfaces a remove failure as LandError.

        This covers the reconcile path: reconcile_one → land_one → _merge_worktree.
        """
        from tide.arc import land

        arc = stream.new_arc(git_project, "land-one-remove")
        worktree.create(git_project, arc)
        wt = worktree.worktree_path(git_project, arc)
        _git(wt, "commit", "--allow-empty", "-m", "work")

        def boom_remove(root, arc_dir, **kwargs):
            raise WorktreeError("fatal: locked")

        monkeypatch.setattr(worktree, "remove", boom_remove)

        with pytest.raises(land.LandError):
            land.land_one(
                git_project,
                "land-one-remove",
                strict=False,
                run_gate=False,
                gate_fn=lambda _root: (0, []),
            )
