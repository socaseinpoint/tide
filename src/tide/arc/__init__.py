"""tide.arc — the on-disk work stream (arcs + goals + candidates).

Ported clean-room from the proven ``arcs`` bash CLI. Planned modules (later units):
  stream.py      — new / open / resume / close / reopen / supersede (U3)
  candidate.py   — capture / list / promote (orchestrator-only promote) (U4)
  board.py       — STREAM board render with computed N/M progress (U8)
  templates.py   — arc.md / <slug>-goal.md / candidate / from-<old> seeds (U3)

Each module exposes plain functions; a ``register(subparsers)`` wires the
``tide arc …`` / ``tide candidate …`` groups into the CLI (see README conventions).
"""
