"""U5 unit — strictness: safe-default strict + round-trip in .tide/state."""

from __future__ import annotations

import pytest

from tide import paths, strictness


def test_defaults_to_strict_when_file_missing(tmp_path):
    # No .tide skeleton at all → dial reads back as the safe default.
    assert strictness.read_strictness(tmp_path) == "strict"
    assert strictness.is_strict(tmp_path) is True


def test_skeleton_default_is_strict(tmp_project):
    # conftest seeds 'strict\n'; reading it agrees with the default.
    assert strictness.read_strictness(tmp_project) == "strict"


def test_set_loose_round_trips(tmp_project):
    written = strictness.set_strictness(tmp_project, "loose")
    assert written == "loose"
    assert strictness.read_strictness(tmp_project) == "loose"
    assert strictness.is_strict(tmp_project) is False
    # persisted as a single newline-terminated line
    assert paths.strictness_file(tmp_project).read_text(encoding="utf-8") == "loose\n"


def test_set_strict_round_trips(tmp_project):
    strictness.set_strictness(tmp_project, "loose")
    strictness.set_strictness(tmp_project, "strict")
    assert strictness.read_strictness(tmp_project) == "strict"


def test_set_normalises_case_and_whitespace(tmp_path):
    assert strictness.set_strictness(tmp_path, "  LOOSE\n") == "loose"
    assert strictness.read_strictness(tmp_path) == "loose"


def test_set_creates_state_dir_when_missing(tmp_path):
    # bare tmp dir (no .tide/state) → set still works, creating the dir.
    strictness.set_strictness(tmp_path, "loose")
    assert paths.strictness_file(tmp_path).is_file()


def test_set_invalid_value_raises(tmp_project):
    with pytest.raises(strictness.StrictnessError):
        strictness.set_strictness(tmp_project, "medium")


def test_read_garbage_falls_back_to_strict(tmp_project):
    paths.strictness_file(tmp_project).write_text("banana\n", encoding="utf-8")
    assert strictness.read_strictness(tmp_project) == "strict"


def test_read_empty_file_falls_back_to_strict(tmp_project):
    paths.strictness_file(tmp_project).write_text("", encoding="utf-8")
    assert strictness.read_strictness(tmp_project) == "strict"
