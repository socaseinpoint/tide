"""tide.cannon.commands — wire the ``tide cannon …`` subcommands.

Follows the build convention: this module owns the argparse surface and thin
handlers; all logic lives in :mod:`store` / :mod:`rev` / :mod:`merge` so it stays
unit-testable without argparse. ``cli.py`` calls :func:`register`.

``cannon merge`` is the single serialization point and is ORCHESTRATOR-ONLY —
the handler hard-refuses a worker via ``cli.require_orchestrator``. ``cannon
status`` lands in U8; it is a labelled stub here.
"""

from __future__ import annotations

import argparse
import sys

from .. import paths, slug
from . import merge, rev, store


def _cmd_init(args: argparse.Namespace) -> int:
    root = paths.require_tide_root()
    cannon = store.init(root, name=args.name, lang=args.lang, force=args.force)
    print("cannon ready: {0}".format(cannon))
    return 0


def _cmd_rev(args: argparse.Namespace) -> int:
    root = paths.require_tide_root()
    print(rev.compute(root))
    return 0


def _resolve_arc_dir(root, ref: str):
    """Find the arc entry dir under ``arcs/`` whose slug matches *ref*."""
    arcs = paths.arcs_dir(root)
    if not arcs.is_dir():
        return None
    # Exact dir name first, then __…__-tolerant slug match.
    exact = arcs / ref
    if exact.is_dir():
        return exact
    for entry in arcs.iterdir():
        if entry.is_dir() and entry.name != "candidates" and slug.ref_matches(ref, entry.name):
            return entry
    return None


def _cmd_merge(args: argparse.Namespace) -> int:
    # cli.main wraps RoleError → exit 1; import lazily to avoid a cycle.
    from ..cli import require_orchestrator

    require_orchestrator("cannon merge")
    root = paths.require_tide_root()
    arc_dir = _resolve_arc_dir(root, args.arc)
    if arc_dir is None:
        print("tide: no arc matching {0!r}".format(args.arc), file=sys.stderr)
        return 1
    arc_slug = slug.entry_slug(arc_dir.name)
    try:
        new_rev = merge.merge_delta(root, arc_dir, slug=arc_slug)
    except FileNotFoundError as exc:
        print("tide: {0}".format(exc), file=sys.stderr)
        return 1
    print("merged {0} → cannon-rev {1}".format(arc_slug, new_rev))
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from . import board

    return board.cmd_status(args)


def register(subparsers) -> None:
    """Add the ``cannon`` command group to *subparsers* (called by cli.py)."""
    p = subparsers.add_parser("cannon", help="durable truth: init/status/merge/rev")
    nsub = p.add_subparsers(dest="cannon_cmd")

    ip = nsub.add_parser("init", help="seed a project's cannon/ (CANON.md + config)")
    ip.add_argument("--name", help="project name in the CANON.md header (default: dir name)")
    ip.add_argument("--lang", default=store.DEFAULT_LANG, help="cannon/config lang (default: en)")
    ip.add_argument("--force", action="store_true", help="overwrite existing CANON.md/config")
    ip.set_defaults(func=_cmd_init, _cmd="cannon init")

    sp = nsub.add_parser("status", help="scan per-arc homes, group by state")
    sp.set_defaults(func=_cmd_status, _cmd="cannon status")

    mp = nsub.add_parser("merge", help="ORCHESTRATOR-ONLY: merge an arc delta into CANON.md")
    mp.add_argument("arc", help="arc slug (or dir name) whose delta.md to merge")
    mp.set_defaults(func=_cmd_merge, _cmd="cannon merge")

    rp = nsub.add_parser("rev", help="print the current cannon-rev (sha256 of CANON.md)")
    rp.set_defaults(func=_cmd_rev, _cmd="cannon rev")
