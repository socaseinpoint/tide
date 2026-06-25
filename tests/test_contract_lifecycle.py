"""U6 unit — contract.lifecycle: new/sign/report/proof/accept/close/reopen/state."""

from __future__ import annotations

import pytest

from tide import fields, strictness
from tide.arc import stream
from tide.cannon import rev, store
from tide.contract import lifecycle, model


def _arc(root, slug="fix-leak"):
    return stream.new_arc(root, slug)


def _write_delta(arc_dir, body="the new truth"):
    model.delta_path(arc_dir).write_text(
        "# delta — fix-leak\nmerged: no\n\n{0}\n".format(body), encoding="utf-8"
    )


# --- new -------------------------------------------------------------------

def test_new_creates_passport_delta_asks_state_draft(tmp_project):
    arc = _arc(tmp_project)
    cpath = lifecycle.new(tmp_project, "fix-leak", goal="stop leak", criteria="no drip")
    assert cpath.is_file()
    assert model.read_state(arc) == "draft"
    assert model.delta_path(arc).is_file()
    assert model.asks_dir(arc).is_dir()
    assert fields.read_field(cpath, "cannon-rev") == rev.compute(tmp_project)


def test_new_one_per_arc_guard(tmp_project):
    _arc(tmp_project)
    lifecycle.new(tmp_project, "fix-leak")
    with pytest.raises(model.ContractError):
        lifecycle.new(tmp_project, "fix-leak")


# --- sign ------------------------------------------------------------------

def test_sign_strict_defaults_to_human_and_runs(tmp_project):
    arc = _arc(tmp_project)
    lifecycle.new(tmp_project, "fix-leak")
    strictness.set_strictness(tmp_project, "strict")
    stamp = lifecycle.sign(tmp_project, "fix-leak", date="2026-06-25")
    assert stamp.startswith("human @ ")
    assert model.read_state(arc) == "running"
    assert model.read_field(arc, "sign") == "human @ 2026-06-25"


def test_sign_loose_defaults_to_orchestrator(tmp_project):
    arc = _arc(tmp_project)
    lifecycle.new(tmp_project, "fix-leak")
    strictness.set_strictness(tmp_project, "loose")
    stamp = lifecycle.sign(tmp_project, "fix-leak", date="2026-06-25")
    assert stamp.startswith("orchestrator @ ")
    assert model.read_state(arc) == "running"


def test_sign_explicit_signer_overrides(tmp_project):
    _arc(tmp_project)
    lifecycle.new(tmp_project, "fix-leak")
    stamp = lifecycle.sign(tmp_project, "fix-leak", signer="grisha", date="2026-06-25")
    assert stamp == "grisha @ 2026-06-25"


def test_sign_refuses_non_draft(tmp_project):
    _arc(tmp_project)
    lifecycle.new(tmp_project, "fix-leak")
    lifecycle.sign(tmp_project, "fix-leak")
    with pytest.raises(model.ContractError):
        lifecycle.sign(tmp_project, "fix-leak")


# --- report / proof / output advance ---------------------------------------

def test_report_and_proof_write_accepted_no_and_advance(tmp_project):
    arc = _arc(tmp_project)
    lifecycle.new(tmp_project, "fix-leak")
    lifecycle.sign(tmp_project, "fix-leak")
    rpath = lifecycle.report(tmp_project, "fix-leak", body="did the thing")
    assert fields.read_field(rpath, "accepted") == "no"
    # only report yet → still running
    assert model.read_state(arc) == "running"
    ppath = lifecycle.proof(tmp_project, "fix-leak", body="here is evidence")
    assert fields.read_field(ppath, "accepted") == "no"
    # both now exist → advanced to output
    assert model.read_state(arc) == "output"


# --- accept ----------------------------------------------------------------

def test_accept_flips_both_to_yes(tmp_project):
    arc = _arc(tmp_project)
    lifecycle.new(tmp_project, "fix-leak")
    lifecycle.sign(tmp_project, "fix-leak")
    lifecycle.report(tmp_project, "fix-leak", body="x")
    lifecycle.proof(tmp_project, "fix-leak", body="y")
    lifecycle.accept(tmp_project, "fix-leak")
    assert fields.read_field(arc / "report.md", "accepted") == "yes"
    assert fields.read_field(arc / "proof.md", "accepted") == "yes"


def test_accept_requires_both_deliverables(tmp_project):
    _arc(tmp_project)
    lifecycle.new(tmp_project, "fix-leak")
    lifecycle.sign(tmp_project, "fix-leak")
    lifecycle.report(tmp_project, "fix-leak", body="x")
    with pytest.raises(model.ContractError):
        lifecycle.accept(tmp_project, "fix-leak")


# --- close -----------------------------------------------------------------

def _ready_to_close(root):
    arc = _arc(root)
    lifecycle.new(root, "fix-leak")
    lifecycle.sign(root, "fix-leak")
    lifecycle.report(root, "fix-leak", body="x")
    lifecycle.proof(root, "fix-leak", body="y")
    lifecycle.accept(root, "fix-leak")
    _write_delta(arc)
    return arc


def test_close_guard_blocks_when_not_accepted(tmp_project):
    arc = _arc(tmp_project)
    lifecycle.new(tmp_project, "fix-leak")
    lifecycle.sign(tmp_project, "fix-leak")
    lifecycle.report(tmp_project, "fix-leak", body="x")
    lifecycle.proof(tmp_project, "fix-leak", body="y")
    _write_delta(arc)
    with pytest.raises(model.ContractError):
        lifecycle.close(tmp_project, "fix-leak")


def test_close_guard_blocks_on_empty_delta(tmp_project):
    _arc(tmp_project)
    lifecycle.new(tmp_project, "fix-leak")
    lifecycle.sign(tmp_project, "fix-leak")
    lifecycle.report(tmp_project, "fix-leak", body="x")
    lifecycle.proof(tmp_project, "fix-leak", body="y")
    lifecycle.accept(tmp_project, "fix-leak")
    # delta.md from `new` is frontmatter-only → empty body
    with pytest.raises(model.ContractError):
        lifecycle.close(tmp_project, "fix-leak")


def test_close_merges_bumps_rev_sets_state(tmp_project):
    arc = _ready_to_close(tmp_project)
    before = rev.compute(tmp_project)
    new_rev = lifecycle.close(tmp_project, "fix-leak", date="2026-06-25")
    # merged into CANON.md journal
    canon = store.read(tmp_project)
    assert "the new truth" in canon
    assert "### 2026-06-25 · fix-leak" in canon
    # rev bumped + stamped + state close
    assert new_rev != before
    assert new_rev == rev.compute(tmp_project)
    assert model.read_field(arc, "cannon-rev") == new_rev
    assert model.read_state(arc) == "close"
    # delta marked merged
    assert fields.read_field(model.delta_path(arc), "merged") == "yes"


def test_close_force_overrides_guard(tmp_project):
    arc = _arc(tmp_project)
    lifecycle.new(tmp_project, "fix-leak")
    lifecycle.sign(tmp_project, "fix-leak")
    _write_delta(arc)  # no report/proof/accept, but delta present
    new_rev = lifecycle.close(tmp_project, "fix-leak", force=True, date="2026-06-25")
    assert model.read_state(arc) == "close"
    assert new_rev == rev.compute(tmp_project)


# --- reopen / state --------------------------------------------------------

def test_reopen_reverses_close(tmp_project):
    arc = _ready_to_close(tmp_project)
    lifecycle.close(tmp_project, "fix-leak", date="2026-06-25")
    lifecycle.reopen(tmp_project, "fix-leak")
    assert model.read_state(arc) == "running"


def test_reopen_refuses_non_closed(tmp_project):
    _arc(tmp_project)
    lifecycle.new(tmp_project, "fix-leak")
    with pytest.raises(model.ContractError):
        lifecycle.reopen(tmp_project, "fix-leak")


def test_transition_sets_state_by_key(tmp_project):
    arc = _arc(tmp_project)
    lifecycle.new(tmp_project, "fix-leak")
    lifecycle.transition(tmp_project, "fix-leak", "output")
    assert model.read_state(arc) == "output"


# --- list ------------------------------------------------------------------

def test_list_contracts_reports_state_and_arc(tmp_project):
    _arc(tmp_project, "fix-leak")
    lifecycle.new(tmp_project, "fix-leak")
    lifecycle.sign(tmp_project, "fix-leak")
    items = lifecycle.list_contracts(tmp_project)
    assert len(items) == 1
    assert items[0]["slug"] == "fix-leak"
    assert items[0]["state"] == "running"
