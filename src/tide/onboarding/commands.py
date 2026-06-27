"""tide.onboarding.commands — the ``tide onboarding`` command + the first-run nudge.

Ties the pure :mod:`flow` content to the two-state :mod:`state` marker and wires the
thin ``tide onboarding`` handler via the standard :func:`register` pattern.

The walkthrough is **pass-or-skip** and **re-runnable**: completing it OR skipping
it both mark passed (skip == passed), and re-invoking it after it is passed simply
walks it again (the marker stays). :func:`nudge` is the single read the session-start
hook performs — one advisory line until passed, then silent.

I/O is injected (``input_fn`` / ``output_fn``) so the walkthrough is unit-testable
without a real terminal; the CLI handler wires the live stdio in.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List

from .. import paths
from . import flow, state

# Tokens that end the walkthrough early. Typing any of these is a SKIP — which is
# still a pass (the marker is written either way).
_SKIP_TOKENS = frozenset({"skip", "s", "q", "quit", "exit"})

# The first-run nudge line. Worded as a peer to the session-start role reminder
# ("tide · …"), self-explanatory, and mentions the escape hatch (skip).
NUDGE_LINE = (
    "tide · new here? run `tide onboarding` to learn the first-project flow "
    "(or skip — it's optional)"
)

InputFn = Callable[..., str]
OutputFn = Callable[..., None]


def _safe_input(prompt: str = "") -> str:
    """``input`` that treats a closed / non-interactive stdin as 'advance'.

    A piped or closed stdin raises ``EOFError``/``OSError`` from ``input``; rather
    than crash the walkthrough we read that as an empty line (step forward), so a
    non-interactive ``tide onboarding`` simply runs through and passes.
    """
    try:
        return input(prompt)
    except (EOFError, OSError):
        return ""


def run_walkthrough(
    root: Path,
    *,
    input_fn: InputFn = _safe_input,
    output_fn: OutputFn = print,
) -> str:
    """Drive the interactive walkthrough; mark passed; return how it ended.

    Prints the intro then each step, prompting between them. An empty line (or
    anything not in :data:`_SKIP_TOKENS`) advances; a skip token ends early. EITHER
    finishing all steps OR skipping writes the marker — there are only two states.

    Returns ``"passed"`` (walked it all) or ``"skipped"`` (bailed early) purely as a
    label for the caller's closing message; the on-disk state is identical.
    """
    output_fn(flow.intro())
    all_steps = flow.steps()
    total = len(all_steps)

    skipped = False
    for i, (title, body) in enumerate(all_steps, start=1):
        output_fn(flow.render_step(i, total, title, body))
        answer = (input_fn("  [enter] next · [skip] done ▸ ") or "").strip().lower()
        if answer in _SKIP_TOKENS:
            skipped = True
            break

    state.mark_passed(root)  # skip == passed: the marker is written either way
    output_fn(flow.footer(skipped=skipped))
    return "skipped" if skipped else "passed"


def nudge(root: Path) -> List[str]:
    """Return the first-run nudge line(s), or ``[]`` once onboarding is passed.

    The single read the session-start hook performs. Two-state: a present marker
    (passed) ⇒ silent; absent (not-passed) ⇒ one advisory line. Pure read — never
    writes, never raises on its own.
    """
    if state.is_passed(root):
        return []
    return [NUDGE_LINE]


# --- CLI wiring ------------------------------------------------------------

def _cmd_onboarding(args) -> int:
    root = paths.require_tide_root()

    if getattr(args, "reset", False):
        if state.reset(root):
            print("tide: onboarding reset — it will nudge again next session")
        else:
            print("tide: onboarding was not marked — nothing to reset")
        return 0

    if getattr(args, "status", False):
        print("passed" if state.is_passed(root) else "not-passed")
        return 0

    if state.is_passed(root):
        # Re-runnable: walk it again on demand; the marker stays passed.
        print("tide: onboarding already completed — re-running (it stays passed)")
    run_walkthrough(root)
    return 0


def register(subparsers) -> None:
    """Add the top-level ``onboarding`` command to *subparsers* (called by cli.py)."""
    p = subparsers.add_parser(
        "onboarding",
        help="guided first-project walkthrough (pass or skip; re-runnable)",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="clear the passed-marker so onboarding nudges again",
    )
    p.add_argument(
        "--status",
        action="store_true",
        help="print onboarding state (passed|not-passed) and exit",
    )
    p.set_defaults(func=_cmd_onboarding, _cmd="onboarding")
