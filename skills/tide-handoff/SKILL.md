---
name: tide-handoff
description: Warm-handoff the current tide chat into a FRESH Claude session in a new terminal, seeded with a distilled version of this conversation and aimed at an arc. Use when the chat is bloated, context is heavy, or you're moving from discussion into work and want a clean session that starts already working — without losing the thread. THREE FORKS — say the fork (or use the flag): • continue = fresh session resumes THIS arc (triggers "/tide-handoff", "/tide-handoff continue", "сверни и передай", "продолжим в свежем терминале"); • new = fresh orchestrator session to promote a candidate ("/tide-handoff new", "начнём с кандидата"); • close = just distil the thread, no spawn ("/tide-handoff close", "закрываю на сегодня"). Part of the tide method — always targets an arc.
---

# tide-handoff

Warm transfer of the thread: distil the CURRENT conversation → seed a **fresh Claude session in a
new terminal**, aimed at an arc, in the right fork. The fresh session starts already working. It is
the tide counterpart of the cold launcher (`tide` / `tide menu`); handoff is the **warm** path, out
of a live chat.

Part of the **tide method** — it always targets an arc and writes into that arc's `workspace/`
(handoff is *continuation*, not an ending — `output/` is reserved for the arc's durable finish).

The CLI does the work: **`tide handoff <arc> [--mode continue|new|close] [--summary-file PATH]
[--no-spawn] [--dry-run] [--adapter orca|tmux]`**. Your job is to pick the fork, distil the thread
into a file, and run the command.

## When
- The chat ballooned / context is heavy → pour it into a clean session.
- Moving from discussion into executing an arc.
- "Closing for today, don't lose it" (the `close` fork).

## The three forks
| Fork | What it does |
|------|--------------|
| `continue` (default) | seed = distil of this thread + next step; the fresh session **resumes THIS arc** |
| `new` | seed = a project-level **orchestrator** session (no arc) so it can **promote a candidate** into the next arc |
| `close` | distil written to the arc workspace, **no spawn** — just save the thread cleanly |

Bare `/tide-handoff` → infer the fork from context, confirm before spawning.

## Algorithm

### 1. Pick the fork
From the argument, else from the conversation: still thinking / task not yet agreed → `continue`;
done here, want to start fresh on a parked idea → `new`; just stopping → `close`. Unsure → confirm
with the human.

### 2. Pick the target arc
- Obvious from context → use it.
- Not obvious → `tide arc status`, show the open arcs, ask which.
- None fits → offer `tide arc new <slug>` (or `tide arc new-goal <slug>` for a goal) first. The arc
  must be **open** — `tide handoff` refuses an unknown/closed arc.

### 3. Distil → a summary file
Read the current conversation and extract **only what carries the thread**:
- **Where we are** — 1–2 paragraphs of state.
- **Decisions** + why.
- **Artifacts** — valuable paths / commands / outputs.
- **Next step** — the one concrete next action.
- **Open questions** (for `continue`).

Write it as markdown to a scratch file (e.g. the OS temp dir). It will be copied verbatim into the
arc's `workspace/handoff-<date>.md`.

### 4. Remind candidates
Before abandoning the chat, surface anything worth keeping for the cannon/method as a candidate:
`tide candidate add <slug> "<the idea>" --from <arc>`. The handoff command also prints the current
candidates backlog as a reminder.

### 5. Run the handoff
```
tide handoff <arc> --mode <fork> --summary-file <path>
```
- `continue` / `new` → with the auto-spawn toggle **ON (default)** this builds the seed and hands it
  to the terminal **adapter** (Orca default, `--adapter tmux` to swap), opening a fresh seeded
  session. The command prints where the distil landed, the candidates reminder, the fork offer, and
  the spawn result.
- `close` → writes the distil only; never spawns.
- `--no-spawn` forces the toggle off for one run (distil only, even for continue/new).
- `--dry-run` builds the seed + adapter command **without** opening a terminal — use it to smoke the
  wiring or preview what would run.

### Toggle (auto-spawn)
Default **ON**. Pin it per project in `.claude/settings.json` → `"handoff_autospawn": false` to make
handoff distil-only by default; `--no-spawn` overrides for a single run.

## Notes
- Orca adapter needs an Accessibility grant for `Orca Helper.app`; if `osascript` is missing/blocked
  the adapter returns a graceful failure with instructions — fall back to `--adapter tmux`.
- The fresh session's own SessionStart hook + CANON.md orient it, but the **thread** comes from the
  distil in `workspace/`. Tell it: progress/logs go to `workspace/`; touch `output/` only when the
  arc actually finishes.
- After the run, drop a `tide candidate add` if anything surfaced for the cannon/method.
