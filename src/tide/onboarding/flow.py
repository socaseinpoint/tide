"""tide.onboarding.flow — the first-project walkthrough content (pure text).

A text-only teaching of the canonical first-project flow described by the landing
copy::

    tide terminal → orient (VECTOR → CANON → cursor) → open an arc →
    handoff → land in canon

Each beat is a ``(title, body)`` pair; :func:`steps` returns them in order and the
small formatters (:func:`intro`, :func:`render_step`, :func:`footer`) lay them out.
Everything here is pure — no I/O, no argparse, no state — so the SAME text drives
both the interactive command (:mod:`tide.onboarding.commands`) and the tests.
"""

from __future__ import annotations

from typing import List, Tuple

Step = Tuple[str, str]


def steps() -> List[Step]:
    """The ordered ``(title, body)`` beats of the first-project walkthrough."""
    return [
        (
            "Open a clean session",
            "Start work with `tide terminal` — not bare `claude`. It opens a "
            "logged-in, scoped session that re-reads itself back into the thread.",
        ),
        (
            "Orient before you touch anything",
            "Read yourself in, in order: VECTOR (why the factory exists) → CANON.md "
            "(where we are now) → the cursor (the live thread). State lives in "
            "files, not the chat.",
        ),
        (
            "Open an arc for the work",
            "Real work is a signed contract, not ad-hoc. Open an arc with "
            "`tide arc new <slug>` — it stamps the canon-rev so later drift is "
            "visible.",
        ),
        (
            "Hand off when the chat gets heavy",
            "Use `tide handoff <arc>` to distil the thread into the arc's workspace "
            "and spawn a fresh session that starts already working.",
        ),
        (
            "Land back into canon",
            "Close the arc and merge its delta so CANON.md becomes the new "
            "living-IS truth: `tide arc land` then `tide canon merge <slug>`.",
        ),
    ]


def intro() -> str:
    """The one-line header shown before the steps."""
    return (
        "tide · onboarding — the first-project flow. Press enter to step through, "
        "or type 'skip' (skipping still counts as done)."
    )


def render_step(n: int, total: int, title: str, body: str) -> str:
    """Format one numbered step (``[n/total] Title`` + indented body)."""
    return "\n[{0}/{1}] {2}\n  {3}".format(n, total, title, body)


def footer(*, skipped: bool) -> str:
    """Closing line — differs in WORDING for skip vs complete, never in state."""
    if skipped:
        return (
            "\ntide · onboarding skipped — marked done. Re-run any time with "
            "`tide onboarding`."
        )
    return (
        "\ntide · onboarding complete — you know the first-project flow. Re-run "
        "any time with `tide onboarding`."
    )
