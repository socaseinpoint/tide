"""tide.hooks.session_start — the SessionStart board + role reminder + warnings.

Ported from the arcs ``arcs-hook`` SessionStart banner, trimmed per
build-blueprint ``sync_hook_wiring`` SESSIONSTART: print the ``tide arc status``
board inline (no plugin system), a one-line orchestrator/worker **role
reminder**, and the net-new **cannon-drift / unmerged-delta warnings**. The arcs
update-nudge and plugin-block emission are DROPPED (the package manager owns
versions; there is no plugin system).

It runs at the top of every Claude session in an opted-in project, so the agent
opens already oriented: what is on the stream, which role it holds, and whether
the cannon moved under an open arc (drift) or a closed arc still owes a merge.

:func:`render` is pure (snapshot-testable); :func:`cmd_session_start` is the thin
handler. Both are defensive: outside a tide project they emit nothing and exit 0
(a SessionStart hook must never break a session).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .. import paths, slug, sync
from ..arc import board
from . import edit_gate

ROLE_REMINDERS = {
    "orchestrator": (
        "tide · role: ORCHESTRATOR — you run the CLI; open/close arcs, merge "
        "cannon, sign contracts. The user doesn't learn the commands — you do."
    ),
    "worker": (
        "tide · role: WORKER — work ONE open arc; write only its own output/ + "
        "delta.md. Never merge cannon / promote candidates (orchestrator-only)."
    ),
}


def _role_reminder(role: str) -> str:
    """One-line reminder for the active TIDE_ROLE (defaults to the worker line)."""
    return ROLE_REMINDERS.get(role, ROLE_REMINDERS["worker"])


def _drift_warnings(root: Path) -> List[str]:
    """Warning lines for OPEN entries whose stamped cannon-rev != the current one."""
    warnings: List[str] = []
    for entry in edit_gate.open_entries(root):
        if sync.has_drifted(entry, root):
            warnings.append(
                "  ⚠ drift: {0} — cannon moved since open; re-read CANON.md "
                "+ re-stamp ('tide arc resume {1}')".format(
                    entry.name, slug.entry_slug(entry.name)
                )
            )
    return warnings


def _unmerged_warnings(root: Path) -> List[str]:
    """Warning lines for CLOSED arcs still carrying an unmerged ``delta.md``."""
    warnings: List[str] = []
    for off in sync.unmerged_deltas(root):
        warnings.append(
            "  ! unmerged delta: {0} → tide cannon merge {1}".format(
                off.name, slug.entry_slug(off.name)
            )
        )
    return warnings


def render(root: Path, role: str) -> str:
    """Render the SessionStart text: board + role reminder + drift/unmerged warnings."""
    root = Path(root)
    lines: List[str] = [board.render_board(root), "", _role_reminder(role)]

    warnings = _drift_warnings(root) + _unmerged_warnings(root)
    if warnings:
        lines.append("")
        lines.append("WARNINGS")
        lines.extend(warnings)

    return "\n".join(lines)


# --- CLI handler -----------------------------------------------------------

def _current_role() -> str:
    """Active TIDE_ROLE via the CLI helper (lazy import avoids any load cycle)."""
    from ..cli import current_role

    return current_role()


def cmd_session_start(args) -> int:
    """``tide hook session-start`` — print the board + reminder + warnings.

    Resolves the project leniently (``find`` not ``require``): outside a tide
    project it prints nothing and exits 0, so the hook is a no-op anywhere it does
    not apply rather than a session-breaking error.
    """
    root: Optional[Path] = paths.find_tide_root()
    if root is None:
        return 0
    print(render(root, _current_role()))
    return 0
