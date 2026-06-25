# rule · contract (worker→arc binding)

A contract records the binding between a worker and an arc: **goal + criteria**, and the proof the
work met them. It is lightweight — tracking, not ceremony — and there is **one contract per arc**
(they move in lockstep: a meaning pivot supersedes both together).

## Lifecycle
```
draft → (sign) → running → report + proof → accept → close
```
- `tide contract new` — draft: goal + criteria for the arc.
- `tide contract sign` — the human signs (interactive, **in the live session only**; there is no
  async / out-of-session sign path). Required under **strict**; skipped under **loose**.
- `tide contract report` / `tide contract proof` — the worker records what it did and the evidence.
- `tide contract accept` — the orchestrator accepts the proof against the criteria.
- `tide contract close` — close the contract (orchestrator-only). `tide contract reopen` to revisit.
- `tide contract state` / `tide contract list` — inspect.

## Strictness decides the sign gate
- **strict** — the human **signs before the worker runs**. No sign, no dispatch.
- **loose** — the orchestrator auto-dispatches; the human reviews after.
Per project: `tide strictness [strict|loose]`.

## Asks (surfacing blockers up)
A worker that needs a human decision raises an **ask** (`tide contract ask "<question>"`); the
orchestrator/human answers (`tide contract answer`). Asks are the channel for questions to bubble
**up** to the human rather than the worker guessing.

## One arc = one contract; supersede is the only pivot
- The arc and its contract are 1:1. Reconsidering an arc's meaning mid-flight is **not** an in-place
  edit — it is a **supersede**: close the old arc/contract (no output) and migrate the tail into a
  new one (`tide arc supersede`), which seeds the new `input/` from the old. Old and new both stay
  on disk, linked. The arc supersede and the contract supersede stay in lockstep.
