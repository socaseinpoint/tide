"""U1 unit — numbering: continuous never-reuse stream + separate candidate seq."""

from __future__ import annotations

from tide import numbering


def test_next_num_empty_dir_starts_at_01(tmp_path):
    (tmp_path / "arcs").mkdir()
    assert numbering.next_num(tmp_path / "arcs") == "01"


def test_next_num_missing_dir_starts_at_01(tmp_path):
    assert numbering.next_num(tmp_path / "nope") == "01"


def test_next_num_counts_open_entries(tmp_path):
    for name in ("01-alpha", "02-beta"):
        (tmp_path / name).mkdir()
    assert numbering.next_num(tmp_path) == "03"


def test_next_num_counts_closed_entries_too(tmp_path):
    (tmp_path / "01-alpha").mkdir()
    (tmp_path / "__02-beta__").mkdir()  # closed
    assert numbering.next_num(tmp_path) == "03"


def test_next_num_counts_goal_entries(tmp_path):
    (tmp_path / "01-alpha").mkdir()
    (tmp_path / "02-@ship").mkdir()  # goal
    assert numbering.next_num(tmp_path) == "03"


def test_next_num_never_reuses_after_close_rename(tmp_path):
    # open 01, 02, 03 then "close" 03 by renaming to __03-…__
    for name in ("01-a", "02-b", "03-c"):
        (tmp_path / name).mkdir()
    (tmp_path / "03-c").rename(tmp_path / "__03-c__")
    # number 03 is consumed even though it was renamed → next is 04, not 03
    assert numbering.next_num(tmp_path) == "04"


def test_next_num_base10_not_octal(tmp_path):
    (tmp_path / "08-h").mkdir()
    (tmp_path / "09-i").mkdir()  # would explode under octal parsing
    assert numbering.next_num(tmp_path) == "10"


def test_next_num_past_99(tmp_path):
    (tmp_path / "100-big").mkdir()
    assert numbering.next_num(tmp_path) == "101"


def test_next_num_ignores_loose_files_and_dotfiles(tmp_path):
    (tmp_path / "01-a").mkdir()
    (tmp_path / "notes.md").write_text("x", encoding="utf-8")
    (tmp_path / "candidates").mkdir()  # no NN- prefix → ignored
    assert numbering.next_num(tmp_path) == "02"


def test_next_num_file_separate_counter(tmp_path):
    cands = tmp_path / "candidates"
    cands.mkdir()
    (cands / "01-idea.md").write_text("x", encoding="utf-8")
    (cands / "02-other.md").write_text("x", encoding="utf-8")
    assert numbering.next_num_file(cands) == "03"


def test_next_num_file_decoupled_from_stream(tmp_path):
    # a busy work stream must NOT bump the candidate counter
    arcs = tmp_path / "arcs"
    arcs.mkdir()
    for name in ("01-a", "02-b", "03-c"):
        (arcs / name).mkdir()
    cands = arcs / "candidates"
    cands.mkdir()
    (cands / "01-idea.md").write_text("x", encoding="utf-8")
    assert numbering.next_num_file(cands) == "02"  # not 04


def test_next_num_file_empty_and_missing(tmp_path):
    (tmp_path / "candidates").mkdir()
    assert numbering.next_num_file(tmp_path / "candidates") == "01"
    assert numbering.next_num_file(tmp_path / "nope") == "01"
