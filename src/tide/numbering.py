"""tide.numbering — continuous, never-reused stream numbering.

Ported from arcs ``next_num`` / ``next_num_file`` (load-bearing):

* :func:`next_num` scans a work-stream dir and returns the next zero-padded
  two-digit number. It counts BOTH open ``NN-<slug>/`` and closed
  ``__NN-<slug>__/`` entries, so **closing renames but never frees a number** —
  numbers are continuous and never reused. Arcs and goals (``NN-@slug``) draw
  from this one counter.
* :func:`next_num_file` is the SEPARATE counter for ``candidates/`` — it scans
  ``NN-<slug>.md`` files, decoupled from the work stream.

Numbers are parsed base-10 (leading zeros are formatting, not octal) and may be
2+ digits (the stream can run past 99).
"""

from __future__ import annotations

import re
from pathlib import Path

# A stream entry dir: optional __ wrapper, NN- (2+ digits), then the slug.
_DIR_ENTRY = re.compile(r"^_{0,2}(\d{2,})-.+")
# A candidate file: NN-<slug>.md
_FILE_ENTRY = re.compile(r"^(\d{2,})-.+\.md$")


def _max_num(names, pattern) -> int:
    """Highest base-10 number among *names* matching *pattern* (0 if none)."""
    best = 0
    for name in names:
        m = pattern.match(name)
        if not m:
            continue
        n = int(m.group(1), 10)  # base-10: leading zeros are padding, not octal
        if n > best:
            best = n
    return best


def next_num(stream_dir: Path) -> str:
    """Next zero-padded NN for a work-stream dir (counts open AND closed)."""
    d = Path(stream_dir)
    if not d.is_dir():
        return "01"
    names = [p.name for p in d.iterdir() if p.is_dir()]
    return "{0:02d}".format(_max_num(names, _DIR_ENTRY) + 1)


def next_num_file(candidates_dir: Path) -> str:
    """Next zero-padded NN for the candidates backlog (separate sequence)."""
    d = Path(candidates_dir)
    if not d.is_dir():
        return "01"
    names = [p.name for p in d.iterdir() if p.is_file()]
    return "{0:02d}".format(_max_num(names, _FILE_ENTRY) + 1)
