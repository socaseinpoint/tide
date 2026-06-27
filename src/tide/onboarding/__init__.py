"""tide.onboarding — the peripheral first-run onboarding add-on.

A self-contained package that teaches the canonical first-project flow
(``tide terminal`` → orient → open an arc → handoff → land in canon). It sits
BESIDE the core, not inside it: the only core touch-points are (a) registering the
``tide onboarding`` command in ``cli.py`` and (b) one lazy-imported nudge line in
the session-start hook. Delete this package + those two touch-points and the core
is unchanged.

Submodules:
* :mod:`state`    — the two-state marker (passed / not-passed; skip == passed).
* :mod:`flow`     — the pure walkthrough content/formatters.
* :mod:`commands` — the ``tide onboarding`` command, walkthrough driver, and nudge.
"""

from __future__ import annotations

from . import commands, flow, state
from .commands import nudge, register

__all__ = ["commands", "flow", "state", "nudge", "register"]
