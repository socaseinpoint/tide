"""tide.onboarding.state — the two-state onboarding marker.

Onboarding has exactly TWO states and no third one:

* **passed**     — the marker file ``.tide/state/onboarding`` exists.
* **not-passed** — it does not.

Presence is the whole truth. SKIP writes the marker too — *skip IS pass* (there is
no separate 'skipped' state on disk). The marker payload is a fixed, meaningless
token: :func:`is_passed` reads only presence, never content, so completing and
skipping leave byte-identical files. The write goes through
:func:`tide.io.atomic_write` so a crash never leaves a torn marker.

This module is a peripheral add-on (see :mod:`tide.onboarding`): it depends on the
core only for path + io primitives and the core never depends back on it.
"""

from __future__ import annotations

from pathlib import Path

from .. import io as _io, paths

# The marker file name (lives under the existing ``.tide/state/`` dir).
MARKER_FILE = "onboarding"

# Fixed payload. Deliberately a constant the readers never parse — its only job is
# to be a non-empty body for a presence flag, so 'completed' and 'skipped' produce
# identical bytes and cannot drift into a third state.
_MARKER_PAYLOAD = "passed\n"


def marker_path(root: Path) -> Path:
    """Path to the onboarding marker (``<root>/.tide/state/onboarding``)."""
    return paths.state_dir(root) / MARKER_FILE


def is_passed(root: Path) -> bool:
    """True when onboarding is marked passed (the marker file exists).

    Reads presence only — never the file's contents — so skip and complete are
    indistinguishable here (both are simply *passed*).
    """
    return marker_path(root).is_file()


def mark_passed(root: Path) -> None:
    """Mark onboarding passed by writing the marker atomically (idempotent).

    Called both when the walkthrough completes AND when the user skips — skip is
    pass. Creates ``.tide/state/`` if missing (``atomic_write`` makes the parent).
    """
    _io.atomic_write(marker_path(root), _MARKER_PAYLOAD)


def reset(root: Path) -> bool:
    """Remove the marker so onboarding reads as not-passed again.

    Lets the user re-experience the first-run nudge from a clean slate. Returns
    True when a marker was actually removed, False when there was none (idempotent).
    """
    p = marker_path(root)
    if not p.is_file():
        return False
    p.unlink()
    return True
