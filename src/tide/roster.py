"""tide.roster — the control-home registry of dispatchable projects.

Ported from ``canon focus`` (decision: drop the helm coupling — tide is its own
control-home). The roster lives at ``<control-home>/roster.md`` and is a flat
list the orchestrator session picks projects from:

    # tide roster
    name | path
    name | path

One ``name | path`` line per project (split on the FIRST ``|`` so paths may
contain spaces). Three operations — ``add`` (register / replace by name), ``rm``
(remove by name), ``ls`` (render) — all order-preserving and re-runnable.

Logic is plain functions (argparse-free, unit-testable); :func:`register` wires
the thin ``tide roster add|rm|ls`` handlers that ``cli.py`` calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from . import paths
from .arc.stream import StreamError

HEADER = "# tide roster"
SEP = " | "


class RosterError(StreamError):
    """A user-facing roster error (empty name/path, removing an absent project).

    Subclasses :class:`tide.arc.stream.StreamError` so ``cli.main`` catches it on
    the same ``except`` arm (prints ``tide: …``, exits nonzero).
    """


# --- parse / serialise -----------------------------------------------------

def _parse_line(line: str):
    """Return ``{'name','path'}`` for a ``name | path`` line, or None.

    Splits on the FIRST ``|`` so a path may itself contain ``|``-free spaces; the
    header, blank lines, and ``|``-less lines are skipped.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "|" not in stripped:
        return None
    name, _, path = stripped.partition("|")
    name = name.strip()
    path = path.strip()
    if not name or not path:
        return None
    return {"name": name, "path": path}


def read_roster(root: Path) -> List[Dict[str, str]]:
    """Return roster entries (``[{'name','path'}, …]``) in file order, or ``[]``.

    A missing roster file is simply an empty roster (not an error).
    """
    f = paths.roster_file(root)
    if not f.is_file():
        return []
    out: List[Dict[str, str]] = []
    for line in f.read_text(encoding="utf-8").splitlines():
        entry = _parse_line(line)
        if entry is not None:
            out.append(entry)
    return out


def _render(entries: List[Dict[str, str]]) -> str:
    """Serialise *entries* into roster text (header + one ``name | path`` line each)."""
    lines = [HEADER]
    for e in entries:
        lines.append("{0}{1}{2}".format(e["name"], SEP, e["path"]))
    return "\n".join(lines) + "\n"


def _write(root: Path, entries: List[Dict[str, str]]) -> None:
    f = paths.roster_file(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(_render(entries), encoding="utf-8")


# --- operations ------------------------------------------------------------

def add(root: Path, name: str, path: str) -> List[Dict[str, str]]:
    """Register *name*→*path*, replacing an existing entry with the same name.

    Order-preserving: an existing name keeps its slot (path updated in place); a
    new name is appended. Creates the roster file (with header) if absent.
    Returns the new entry list.
    """
    n = (name or "").strip()
    p = (path or "").strip()
    if not n:
        raise RosterError("roster: empty project name")
    if not p:
        raise RosterError("roster: empty project path")

    entries = read_roster(root)
    updated = [dict(e) for e in entries]
    for e in updated:
        if e["name"] == n:
            e["path"] = p
            break
    else:
        updated.append({"name": n, "path": p})
    _write(root, updated)
    return updated


def remove(root: Path, name: str) -> List[Dict[str, str]]:
    """Remove the project named *name*; raise :class:`RosterError` if absent.

    Returns the new entry list. The header is preserved even when the roster
    becomes empty.
    """
    n = (name or "").strip()
    entries = read_roster(root)
    kept = [dict(e) for e in entries if e["name"] != n]
    if len(kept) == len(entries):
        raise RosterError("roster: no project named {0!r}".format(name))
    _write(root, kept)
    return kept


def render_list(root: Path) -> str:
    """One-line-per-project rendering (``name | path``), or a ``(no projects)`` note."""
    entries = read_roster(root)
    if not entries:
        return "(no projects)"
    return "\n".join(
        "{0}{1}{2}".format(e["name"], SEP, e["path"]) for e in entries
    )


# --- CLI wiring ------------------------------------------------------------

def _root() -> Path:
    return paths.require_tide_root()


def _cmd_add(args) -> int:
    add(_root(), args.name, args.path)
    print("tide: rostered {0} → {1}".format(args.name, args.path))
    return 0


def _cmd_rm(args) -> int:
    remove(_root(), args.name)
    print("tide: removed {0} from roster".format(args.name))
    return 0


def _cmd_ls(args) -> int:
    print(render_list(_root()))
    return 0


def register(subparsers) -> None:
    """Add the top-level ``roster`` command group to *subparsers* (called by cli.py)."""
    p = subparsers.add_parser("roster", help="manage the control-home project roster")
    rsub = p.add_subparsers(dest="roster_cmd")

    ap = rsub.add_parser("add", help="register a project (name path)")
    ap.add_argument("name")
    ap.add_argument("path")
    ap.set_defaults(func=_cmd_add, _cmd="roster add")

    rp = rsub.add_parser("rm", help="remove a project (name)")
    rp.add_argument("name")
    rp.set_defaults(func=_cmd_rm, _cmd="roster rm")

    lp = rsub.add_parser("ls", help="list registered projects")
    lp.set_defaults(func=_cmd_ls, _cmd="roster ls")
