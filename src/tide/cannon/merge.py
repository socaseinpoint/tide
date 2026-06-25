"""tide.cannon.merge — append an arc delta under ``## Cannon journal``.

This is the proven canon ``merge_delta`` mechanic, ported verbatim and made
tide's **single serialization point**: workers only ever write their own arc's
``delta.md``; the one place writes converge into the living truth is this merge,
which runs only in the live orchestrator session (and is CLI-gated to it).

Mechanic (build-blueprint MERGE MECHANIC):

* Append the delta under the ``## Cannon journal`` header as a stamped entry
  ``### <date> · <slug>`` followed by the delta body.
* If the journal header is missing, create it at end-of-file first.
* **Append-only** — prior journal entries are never touched or reordered. The
  append-only journal is the conflict-free baseline; conflicts surface to the
  human one delta at a time at this gate.

After a file-level merge the source delta is marked merged (``merged: yes``) so
the sync engine won't double-merge it. Text helpers are pure; file wrappers do
the I/O and recompute the bumped cannon-rev.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

from .. import fields, paths
from . import rev

JOURNAL_HEADER = "## Cannon journal"


def _today() -> str:
    """Today's date as ``YYYY-MM-DD`` (injectable via callers passing *date*)."""
    return datetime.date.today().isoformat()


def has_journal(text: str) -> bool:
    """True when *text* contains a top-level ``## Cannon journal`` heading line."""
    target = JOURNAL_HEADER.strip()
    return any(line.strip() == target for line in text.splitlines())


def _entry_block(date: str, slug: str, delta_body: str) -> str:
    """Render one journal entry: ``### <date> · <slug>`` then the delta body."""
    stamp = "### {0} · {1}".format(date, slug)
    body = delta_body.strip("\n")
    if body:
        return "{0}\n\n{1}\n".format(stamp, body)
    return "{0}\n".format(stamp)


def _journal_insert_index(lines):
    """Index (in *lines*) at which a new entry belongs inside the journal section.

    = the line of the next top-level ``## `` heading after the journal header, or
    ``len(lines)`` (EOF) when the journal is the last section. Returns None when
    there is no journal header at all.
    """
    header = JOURNAL_HEADER.strip()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            return j
    return len(lines)


def merge_delta_text(canon_text: str, delta_body: str, *, date: str, slug: str) -> str:
    """Return *canon_text* with a stamped delta entry appended under the journal.

    Creates the ``## Cannon journal`` header at EOF if absent. Append-only: the
    new entry goes at the END of the journal section (before the next sibling H2,
    if any), leaving every prior entry byte-identical.
    """
    block = _entry_block(date, slug, delta_body)
    had_trailing_nl = canon_text.endswith("\n")
    # Normalise to a list of content lines (drop the trailing "" from a final \n).
    lines = canon_text.split("\n")
    if had_trailing_nl and lines and lines[-1] == "":
        lines = lines[:-1]

    idx = _journal_insert_index(lines)
    if idx is None:
        # No journal yet → create the header at EOF, then the entry under it.
        tail = [""] if lines else []
        lines = lines + tail + [JOURNAL_HEADER, ""] + block.rstrip("\n").split("\n")
    else:
        entry_lines = block.rstrip("\n").split("\n")
        # Ensure a blank separator line precedes the entry when the slot above
        # it is non-blank (keeps entries visually distinct, markdown-clean).
        sep = []
        if idx > 0 and lines[idx - 1].strip() != "":
            sep = [""]
        lines = lines[:idx] + sep + entry_lines + [""] + lines[idx:]
        # Drop a possible duplicate trailing blank we may have introduced at EOF.

    out = "\n".join(lines)
    # Always end the document with exactly one newline.
    return out.rstrip("\n") + "\n"


def mark_merged(delta_path: Path, date: Optional[str] = None) -> None:
    """Stamp ``merged: yes`` into a delta file so it is not merged twice."""
    fields.set_field(Path(delta_path), "merged", "yes")


def merge_delta(
    root: Path,
    arc_dir: Path,
    *,
    slug: str,
    date: Optional[str] = None,
    delta_name: str = "delta.md",
) -> str:
    """Merge ``<arc_dir>/<delta_name>`` into the project's CANON.md journal.

    Reads the arc's delta body, appends it under the journal (creating the header
    if missing), marks the delta merged, and returns the bumped cannon-rev
    (recomputed over the new CANON.md). Raises if the delta file is missing.
    """
    date = date or _today()
    delta_path = Path(arc_dir) / delta_name
    if not delta_path.is_file():
        raise FileNotFoundError("no delta to merge at {0}".format(delta_path))

    delta_body = _delta_body(delta_path.read_text(encoding="utf-8"))

    canon = paths.canon_file(root)
    canon_text = canon.read_text(encoding="utf-8") if canon.is_file() else ""
    merged = merge_delta_text(canon_text, delta_body, date=date, slug=slug)
    canon.parent.mkdir(parents=True, exist_ok=True)
    canon.write_text(merged, encoding="utf-8")

    mark_merged(delta_path, date=date)
    return rev.compute(root)


def _delta_body(text: str) -> str:
    """Extract the merge-worthy body of a delta.md (drop frontmatter + H1).

    A delta file may carry a ``# delta — <slug>`` heading and ``key:`` frontmatter
    (e.g. ``merged:``); only the prose below belongs in the journal entry.
    """
    lines = text.splitlines()
    out = []
    in_body = False
    for line in lines:
        if not in_body:
            stripped = line.strip()
            if stripped == "":
                continue
            if stripped.startswith("#"):
                continue
            if fields._line_key(line) is not None:
                continue
            in_body = True
        out.append(line)
    return "\n".join(out).strip("\n")
