# Session operations — флот (offload) / handoff / branch

The three human-triggered operations on a **session** (one run inside a prism).
Outside these, the agent leaves the stream alone (minimal mode). Captured from the
design conversation; OPEN questions marked ⛏.

## Model recap
- **prism (призма)** — container, the arc through which arcs are managed.
- **session** — one run inside a prism; numbered; chained by `from:`.
- Each session passport carries `## cursor` (resume point) + `## context` (memory).

## флот (offload)
- Dump the session's **current** work into its arc: append to `## context`, refresh `## cursor`.
- **Incremental** — only what's new since the last offload. Nothing new → writes nothing and
  says so.
- It's the intermediate step that **handoff and branch both run first**.
- **Marker — DECIDED: deterministic (B).** The session passport carries `offloaded-at: <N>` where
  `N` is the session's **transcript size** (message/line count of the live Claude session) at the
  last offload. On offload: read current size, distill the slice `[offloaded-at .. now]`, append it
  to `## context`, set `offloaded-at = now`. If `now == offloaded-at` → nothing new, say so.
  - Split of labor: the **skill** measures the transcript size (Claude Code session internals) and
    distills the slice; the **CLI** stores/reads the marker + appends text (deterministic, testable).

## handoff = offload + new session carrying prior context
- Run offload first, then create a NEW session with `from: <this session>`.
- Opens a fresh **Orca terminal** (the existing `/handoff` skill already does this).
- The handoff distillation states: **what was done · what's left undone · where it's heading**.
- New session is seeded with that carried context.

## branch = offload + new session forked from a marked point
- Like handoff (offload + new session, `from:` set) but a **fork** from the point the session was
  at — both branch and handoff record `from:` so lineage is visible.

## picker sub-choice (on continuing an existing session)
- When you pick an existing session in `tide menu`, it asks:
  **continue in the same context** OR **handoff into a new session**.
- ⛏ "same context" = literal `claude --resume <id>` of that conversation, OR re-seed a fresh
  session from the session's arc/cursor? (Different mechanisms — needs a decision.)

## Build sketch (once OPEN questions close)
- CLI primitive: `tide session offload <prism> <session> [text]` — dumb appender (incrementality
  lives in the skill, variant A). `tide arc new-session --from <ref>` already sets `from:`.
- Skills: `/offload`, `/branch` (and wire `/handoff` to write into the prism session + set `from:`).
- Minimal: no contracts, no canon, no auto-actions.
