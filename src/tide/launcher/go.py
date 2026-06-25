"""tide.launcher.go — ``tide go``: the light ENTRY dispatcher (mirror of handoff).

``tide handoff`` is the clean EXIT — it distils a chat and forks out. ``tide go``
is the missing symmetric ENTRY: a light gate the human walks through to get back
INTO tide, asking only *"resume prior work, or start new?"*. It is a ROUTER, not a
brain — it resolves a seed, then hands the launch to ``tide terminal`` (the clean
logged-in in-place session). It never opens its own kind of session and never
duplicates the scoped+skip-perms launch shape.

Two doors:

* **resume** — open arcs that carry a *resumable thread*. Each open arc is
  classified by its LATEST ``workspace/handoff-*.md`` (the distil ``tide handoff``
  wrote): ``continue`` → a live thread, seeded from that distil; ``close`` → put
  down on purpose, **hidden** (the human said "его нет"); none (chat ended without
  a handoff) → ``raw``, resumed from the arc's passport ("поднять сыро").
* **new** — every open arc as a fresh start (seeded from its passport), plus a
  ``just chat`` option (no arc — the plain head seed, ``MIGRATE.md``).

Before EITHER door launches, a light **in-flight gate** runs at the single launch
choke point: a file-signal read (over ``tide status``, NOT process-locking) for
work still being processed — unmerged deltas, running/output contracts, drift. If
anything is in flight the human is shown it and asked to wait/enter-anyway/cancel,
so a controlled entry never drops them into a half-merged, half-closed state. (A
real concurrent-session lock is a separate candidate, not this.)

Layering matches the package: the listing/classification/rendering helpers are
pure (argparse- and exec-free, snapshot-testable); :func:`cmd_go` is the thin
interactive handler, and the actual launch is delegated to
:func:`tide.launcher.terminal.cmd_terminal` so the scoped argv lives in ONE place.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .. import fields, slug
from ..adapters.base import persist_seed
from ..arc import board
from ..arc.stream import StreamError
from . import seed, terminal

WORKSPACE_DIRNAME = "workspace"
HANDOFF_GLOB = "handoff-*.md"

# Thread kinds (how an open arc is resumable).
KIND_CONTINUE = "continue"  # latest handoff mode==continue → seed from the distil
KIND_RAW = "raw"            # no handoff (chat ended without one) → seed from passport

# The "no arc, plain head" choice in the NEW menu — index 0, reserved.
JUST_CHAT = "just chat"

# Contract states that mean "still being processed" (not yet sealed) — the
# in-flight gate flags these so the human isn't dropped onto half-done work.
LIVE_CONTRACT_STATES = ("running", "output")

# In-flight WAIT bounds: poll the file signals this often, up to this long, before
# giving up and re-asking. Kept short — this is a courtesy wait for another session
# to finish its merge, not a process lock.
WAIT_INTERVAL_S = 2.0
WAIT_MAX_S = 60.0


class GoError(StreamError):
    """A dispatcher error (bad pick, empty menu). Caught by ``cli.main`` like the rest."""


# --- handoff inspection (pure-ish reads) -----------------------------------

def latest_handoff(arc_dir: Path) -> Optional[Path]:
    """The most recent ``workspace/handoff-<date>.md`` for *arc_dir*, or None.

    Filenames are ``handoff-<ISO-date>.md`` so a lexical sort is chronological;
    the last is the latest distil — the one that decides the arc's resume state.
    """
    ws = Path(arc_dir) / WORKSPACE_DIRNAME
    if not ws.is_dir():
        return None
    files = sorted(ws.glob(HANDOFF_GLOB))
    return files[-1] if files else None


def handoff_mode(path: Path) -> str:
    """The ``mode:`` field of a handoff distil (continue|new|close), lowercased."""
    return (fields.read_field(path, "mode") or "").strip().lower()


def handoff_oneliner(path: Path) -> str:
    """First real line of the distil's ``## Where we are`` section (one-liner).

    Falls back to "" when the section is absent or still the un-distilled
    placeholder, so the caller can drop back to the arc's goal line.
    """
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("## where we are"):
            in_section = True
            continue
        if in_section:
            if not stripped:
                continue
            if stripped.startswith("## "):  # next section, nothing useful found
                return ""
            if stripped.startswith("(") and "not distilled" in stripped.lower():
                return ""  # the placeholder build_summary writes when empty
            return stripped
    return ""


# --- resume listing (pure) -------------------------------------------------

@dataclass
class Thread:
    """A resumable thread: an open arc + how to re-enter it.

    * ``arc_dir`` / ``name`` / ``ref`` — the open arc dir, its dir name, its bare slug.
    * ``kind`` — ``continue`` (seed from the distil) or ``raw`` (seed from passport).
    * ``handoff`` — the distil path for a ``continue`` thread (None for ``raw``).
    * ``summary`` — the one-line gist shown in the menu (distil line or goal line).
    """

    arc_dir: Path
    name: str
    ref: str
    kind: str
    handoff: Optional[Path]
    summary: str


def _goal_line(arc_dir: Path) -> str:
    """The arc's one-line ``goal:`` (empty when still the scaffold placeholder)."""
    from ..arc.stream import passport_path

    goal = (fields.read_field(passport_path(arc_dir), "goal") or "").strip()
    if goal.startswith("<") and goal.endswith(">"):
        return ""  # un-filled scaffold hint — not a real summary
    return goal


def resumable_threads(root: Path) -> List[Thread]:
    """Open arcs that are resumable, classified by their latest handoff (pure read).

    Walks the control-home's open arcs. An arc whose latest handoff mode is
    ``close`` is intentionally put down → **excluded**. ``continue`` → a live
    thread seeded from the distil. Anything else (no handoff, or a non-continue
    non-close mode) → ``raw``, seeded from the passport. The menu summary prefers
    the distil's "Where we are" line, falling back to the arc's goal line.
    """
    out: List[Thread] = []
    for arc in board.open_entries(Path(root)):
        ref = slug.entry_slug(arc.name)
        goal = _goal_line(arc)
        handoff = latest_handoff(arc)
        if handoff is not None:
            mode = handoff_mode(handoff)
            if mode == "close":
                continue  # put down on purpose — "его нет"
            if mode == KIND_CONTINUE:
                summary = handoff_oneliner(handoff) or goal or "(thread not distilled)"
                out.append(Thread(arc, arc.name, ref, KIND_CONTINUE, handoff, summary))
                continue
        # no handoff, or a non-continue/non-close mode → raise it raw from the cursor
        out.append(Thread(arc, arc.name, ref, KIND_RAW, None, goal or "(no goal set)"))
    return out


def render_resume_menu(threads: List[Thread]) -> str:
    """The numbered resume pick-list, or an empty-state note steering to ``new``."""
    if not threads:
        return "(no resumable threads — start fresh: 'tide go --mode new')"
    lines = ["Resume — pick a thread to pick back up:"]
    for i, t in enumerate(threads, start=1):
        lines.append("  {0}) {1}  [{2}]  {3}".format(i, t.name, t.kind, t.summary))
    return "\n".join(lines)


# --- new listing (pure) ----------------------------------------------------

def new_options(root: Path) -> List[Path]:
    """Open arcs offered as fresh starts in the NEW menu (numeric order)."""
    return board.open_entries(Path(root))


def render_new_menu(arcs: List[Path], root: Path) -> str:
    """The numbered new-start pick-list: open arcs + the ``0) just chat`` option."""
    lines = ["New — start fresh:"]
    lines.append("  0) {0} (no arc — plain head session)".format(JUST_CHAT))
    for i, arc in enumerate(arcs, start=1):
        goal = _goal_line(arc) or "(no goal set)"
        lines.append("  {0}) {1}  {2}".format(i, arc.name, goal))
    return "\n".join(lines)


# --- selection parsing (pure) ----------------------------------------------

def parse_pick(raw: str, count: int, *, allow_zero: bool = False) -> int:
    """Parse a single 1-based pick into an int, validated to ``[lo..count]``.

    *allow_zero* widens the floor to 0 (the NEW menu's ``just chat`` slot). Raises
    :class:`GoError` on an empty, non-numeric, or out-of-range pick.
    """
    s = (raw or "").strip()
    lo = 0 if allow_zero else 1
    if not s:
        raise GoError("go: empty pick (choose a number {0}..{1})".format(lo, count))
    if not s.isdigit():
        raise GoError("go: invalid pick {0!r} (want a number {1}..{2})".format(s, lo, count))
    n = int(s)
    if not (lo <= n <= count):
        raise GoError("go: pick {0} out of range ({1}..{2})".format(n, lo, count))
    return n


# --- seed resolution (one seed file per choice) ----------------------------

RESUME_HEADER = """# tide go — resume thread: {arc}

You are re-entering the tide HEAD (coordinator) to RESUME a prior thread. Your
standing role is in the control-home MIGRATE.md — read it first, stay light
(coordinate, don't do project work here), then pick up the distilled thread below.

---
"""


def build_resume_seed(arc_ref: str, distil_text: str) -> str:
    """Compose a continue-thread seed: the head-role pointer + the distil (pure)."""
    return RESUME_HEADER.format(arc=arc_ref) + distil_text.strip() + "\n"


def seed_for_thread(root: Path, thread: Thread, *, dry_run: bool = False) -> Optional[str]:
    """Persist and return the seed-file path for *thread* (None ⇒ default seed).

    A ``continue`` thread is seeded from its distil (wrapped with the head-role
    pointer); a ``raw`` thread from the arc passport via :func:`seed.seed_for_project`
    (the same orchestrator seed the menu/handoff paths build). On *dry_run* nothing
    is written — a placeholder token is returned so the delegated terminal dry-run
    still shows the ``@<seed-file>`` shape.
    """
    if thread.kind == KIND_CONTINUE and thread.handoff is not None:
        distil = Path(thread.handoff).read_text(encoding="utf-8")
        text = build_resume_seed(thread.ref, distil)
    else:
        text = seed.seed_for_project(root, arc_ref=thread.ref, control_home=root)
    if dry_run:
        return "<seed-file>"
    return str(persist_seed(text, "tide-go-{0}".format(slug.slugify(thread.ref) or "resume")))


def seed_for_new_arc(root: Path, arc_dir: Path, *, dry_run: bool = False) -> str:
    """Persist and return the seed-file path for a fresh start on *arc_dir*."""
    ref = slug.entry_slug(arc_dir.name)
    text = seed.seed_for_project(root, arc_ref=ref, control_home=root)
    if dry_run:
        return "<seed-file>"
    return str(persist_seed(text, "tide-go-new-{0}".format(slug.slugify(ref) or "arc")))


# --- in-flight gate (file signals over `tide status`, NOT a process lock) ---

@dataclass
class InFlight:
    """A snapshot of "work still being processed" — three file signals (pure read).

    * ``unmerged`` — closed arcs whose ``delta.md`` is written but un-merged (the
      between-arcs barrier offenders).
    * ``contracts`` — ``(arc, state)`` of contracts still ``running``/``output``
      (signed but not sealed).
    * ``drift`` — open arcs whose stamped ``cannon-rev`` lags the current one.

    ``clean`` is the gate's verdict: nothing in flight ⇒ enter silently.
    """

    unmerged: List[str]
    contracts: List[Tuple[str, str]]
    drift: List[str]

    @property
    def clean(self) -> bool:
        return not (self.unmerged or self.contracts or self.drift)


def inflight_signals(root: Path) -> InFlight:
    """Read the three in-flight signals for *root* over the same on-disk truth as
    ``tide status`` (pure, no locking). Lazy imports keep the launcher light.
    """
    from .. import sync
    from ..arc.stream import passport_path
    from ..cannon import rev
    from ..contract import lifecycle

    unmerged = [p.name for p in sync.unmerged_deltas(Path(root))]
    contracts = [
        (str(c["arc"]), str(c["state"]))
        for c in lifecycle.list_contracts(Path(root))
        if c.get("state") in LIVE_CONTRACT_STATES
    ]
    current = rev.compute(Path(root))
    drift: List[str] = []
    for entry in board.open_entries(Path(root)):
        stamped = fields.read_field(passport_path(entry), "cannon-rev")
        if stamped and stamped != current:
            drift.append(entry.name)
    return InFlight(unmerged, contracts, drift)


def render_inflight(s: InFlight) -> str:
    """One short block: ``clean`` line, or the in-flight signals that are present."""
    if s.clean:
        return "in-flight check: clean (no unmerged deltas / running contracts / drift)"
    lines = ["⚠ in-flight check — work still being processed:"]
    if s.unmerged:
        lines.append("  unmerged deltas: {0}".format(", ".join(s.unmerged)))
    if s.contracts:
        lines.append(
            "  running/output contracts: {0}".format(
                ", ".join("{0} [{1}]".format(a, st) for a, st in s.contracts)
            )
        )
    if s.drift:
        lines.append("  drift: {0}".format(", ".join(s.drift)))
    return "\n".join(lines)


def wait_until_settled(
    root: Path,
    *,
    interval: float = WAIT_INTERVAL_S,
    max_wait: float = WAIT_MAX_S,
    sleep_fn: Callable[[float], None] = time.sleep,
    signal_fn: Callable[[Path], InFlight] = inflight_signals,
) -> bool:
    """Poll the in-flight signals until clean or *max_wait* elapses; True iff clean.

    A bounded courtesy wait for another session to finish its merge — never an
    unbounded block. ``sleep_fn``/``signal_fn`` are injected so tests drive it
    without real time or disk.
    """
    waited = 0.0
    while True:
        if signal_fn(Path(root)).clean:
            return True
        if waited >= max_wait:
            return False
        sleep_fn(interval)
        waited += interval


def _prompt_choice(prompt: str, allowed: Tuple[str, ...], default: str) -> str:
    """Read one lowercased letter from *allowed*; *default* on EOF or anything else."""
    try:
        ans = input(prompt).strip().lower()
    except EOFError:
        return default
    first = ans[:1]
    return first if first in allowed else default


def _inflight_gate(root: Path, *, dry_run: bool) -> bool:
    """Run the in-flight gate; return True to proceed with the launch, False to abort.

    Always PRINTS the check (clean or not) so it's visible — including under
    ``--dry-run``, where it never prompts (just shows the status, then proceeds).
    When live and interactive: ``c`` aborts, ``g`` enters anyway, ``w`` waits for
    the signals to settle (bounded) then enters — falling back to a final g/c ask
    if the wait times out.
    """
    signals = inflight_signals(root)
    print(render_inflight(signals))
    if signals.clean or dry_run:
        return True
    choice = _prompt_choice(
        "Есть незавершённая обработка — подождать завершения [w] / войти осознанно [g] / отмена [c]? ",
        ("w", "g", "c"),
        default="c",
    )
    if choice == "c":
        print("go: cancelled — nothing launched (work still in flight)")
        return False
    if choice == "g":
        return True
    # 'w' — wait for the other session's merge to land, bounded.
    print("waiting for in-flight work to settle…")
    if wait_until_settled(root):
        print("in-flight settled — entering")
        return True
    print(render_inflight(inflight_signals(root)))
    again = _prompt_choice(
        "Still in flight after waiting — войти осознанно [g] / отмена [c]? ",
        ("g", "c"),
        default="c",
    )
    if again != "g":
        print("go: cancelled — nothing launched (work still in flight)")
        return False
    return True


# --- launch delegation -----------------------------------------------------

def _launch(seed_file: Optional[str], root: Path, *, dry_run: bool) -> int:
    """Hand the resolved seed to ``tide terminal`` (the single scoped-launch path).

    First runs the in-flight gate at this single choke point (both doors funnel
    here); if it aborts, nothing is launched. Otherwise builds the Namespace
    ``terminal.cmd_terminal`` expects and calls it directly — so the scoped+skip-
    perms argv, the cwd, and the ``os.execvp`` exec live in ONE place
    (``launcher.terminal``), never duplicated here. ``seed_file=None`` lets terminal
    resolve its own default (MIGRATE.md/RESUME.md) — the ``just chat`` path.
    """
    if not _inflight_gate(root, dry_run=dry_run):
        return 0
    ns = argparse.Namespace(
        seed=seed_file,
        dry_run=dry_run,
        no_disable_slash=False,
        no_skip_permissions=False,
    )
    return terminal.cmd_terminal(ns)


# --- CLI handler -----------------------------------------------------------

def _resolve_mode(args, dry_run: bool) -> Optional[str]:
    """Resolve the resume/new mode: explicit ``--mode``, else the light r/n prompt.

    On a dry-run with no ``--mode`` we return None so :func:`cmd_go` prints the
    OVERVIEW (both menus) instead of blocking on stdin — the inspectable view.
    """
    mode = getattr(args, "mode", None)
    if mode:
        return mode
    if dry_run:
        return None
    print("tide go — back into tide.")
    try:
        ans = input("Вернуться к прошлой работе или начать новую? [r/n] ").strip().lower()
    except EOFError:
        ans = ""
    return "resume" if ans.startswith("r") else "new"


def _render_overview(root: Path) -> str:
    """Both menus + the in-flight check — the dry-run, no-mode inspectable view."""
    threads = resumable_threads(root)
    arcs = new_options(root)
    return "\n\n".join(
        [
            render_resume_menu(threads),
            render_new_menu(arcs, root),
            render_inflight(inflight_signals(root)),
        ]
    )


def _do_resume(root: Path, args, dry_run: bool) -> int:
    """Resume flow: list threads, pick one, seed from it, delegate to terminal."""
    threads = resumable_threads(root)
    print(render_resume_menu(threads))
    if not threads:
        return 0
    raw = getattr(args, "pick", None)
    if not raw and not dry_run:
        try:
            raw = input("resume> ")
        except EOFError:
            raw = ""
    if not raw:  # dry-run overview within a mode: show the menu, don't pick
        return 0
    n = parse_pick(raw, len(threads))
    thread = threads[n - 1]
    seed_file = seed_for_thread(root, thread, dry_run=dry_run)
    if dry_run:
        print("\nwould resume [{0}] {1} →".format(thread.kind, thread.name))
    return _launch(seed_file, root, dry_run=dry_run)


def _do_new(root: Path, args, dry_run: bool) -> int:
    """New flow: list open arcs + just-chat, pick one, seed it, delegate to terminal."""
    arcs = new_options(root)
    print(render_new_menu(arcs, root))
    raw = getattr(args, "pick", None)
    if not raw and not dry_run:
        try:
            raw = input("new> ")
        except EOFError:
            raw = ""
    if not raw:  # dry-run overview within a mode
        return 0
    n = parse_pick(raw, len(arcs), allow_zero=True)
    if n == 0:
        # seed_file None ⇒ terminal resolves the MIGRATE.md head seed (just-chat).
        if dry_run:
            print("\nwould start [just chat] → plain head session (MIGRATE.md seed)")
        return _launch(None, root, dry_run=dry_run)
    arc = arcs[n - 1]
    seed_file = seed_for_new_arc(root, arc, dry_run=dry_run)
    if dry_run:
        print("\nwould start [new arc] {0} →".format(arc.name))
    return _launch(seed_file, root, dry_run=dry_run)


def cmd_go(args) -> int:
    """``tide go`` — light entry dispatcher: resume a prior thread or start new."""
    root = terminal.find_control_home()
    dry_run = bool(getattr(args, "dry_run", False))
    mode = _resolve_mode(args, dry_run)

    if mode is None:  # dry-run, no mode → print the overview, exec nothing
        print(_render_overview(root))
        return 0
    if mode == "resume":
        return _do_resume(root, args, dry_run)
    if mode == "new":
        return _do_new(root, args, dry_run)
    raise GoError("go: unknown mode {0!r} (want resume|new)".format(mode))


def register(subparsers) -> None:
    """Add the top-level ``go`` command to *subparsers* (called by cli.py)."""
    p = subparsers.add_parser(
        "go",
        help="light entry dispatcher: resume a prior thread or start new (mirror of handoff)",
    )
    p.add_argument(
        "--mode",
        choices=("resume", "new"),
        help="skip the r/n prompt: resume a prior thread | start new",
    )
    p.add_argument("--pick", help="non-interactive selection within the mode (e.g. '1', or '0' for just-chat)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="print the menus + what would launch, without exec'ing a session",
    )
    p.set_defaults(func=cmd_go, _cmd="go")
