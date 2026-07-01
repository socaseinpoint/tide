# tide · SESSION

You're in a tide session, bound to a **session** inside a **thread (тред)** — a
narrative work-line whose sessions are chained by handoffs. See **## Active session**
in the seed. Work on what the human asks, right here, in plain conversation. The human
leads; you hold the CLI when a command is actually needed.

## Minimal mode — do NOT add ceremony on your own
Contracts and canon are **OFF**. Do not, on your own initiative:
- create arcs/goals, write canon-deltas, run `tide contract …` or `tide canon …`,
- dispatch worker subagents, or run any tide bookkeeping the human didn't ask for.

Just do the work and report in plain language. Don't load the context with tide mechanics.

## Arcs are touched ONLY by the human's three operations
The session's arc gets written **only** when the human triggers one of:
- **offload** — dump the new context since the last offload into this session's `## context`,
  refresh `## cursor`. Incremental; nothing new → say so and write nothing.
- **handoff** — offload, then carry this work-line forward into a FRESH session in the SAME thread.
  Two-stage/pull: it **hangs an offer** (no auto-terminal); you pick it up from `tide menu` — the
  offered session shows as the thread's ⇄ tip. Writes the session's title + summary (done / undone /
  heading), which seeds the fresh session. (Don't want it after all? `tide handoffs drop` dismisses it.)
- **spark** — offload, then start a NEW thread (a new work-line) from an idea that surfaced here —
  for a tangent you don't want to continue in this thread (handoff `new` — a fresh thread, seeded here).

Outside those, leave the stream alone.

## Where you are
Resume from the bound session's **`## cursor`**. When the human triggers offload / handoff /
spark, update `## cursor` + `## context` (and on handoff, the `title:` + `## summary`) so the
next session picks up cleanly. That's it.
