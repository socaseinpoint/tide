"""tide.contract — lightweight worker→arc binding (goal + criteria).

5-state lifecycle: draft → (sign) → running → output → close.
One contract per arc. Modules (U6, implemented):
  model.py      — contract.md passport read/write, state machine, arc resolve
  lifecycle.py  — new / sign / report / proof / accept / close / reopen / state / list
  ask.py        — durable per-arc asks/NN-slug.md ask/answer (no escalate/TG)

Strictness (per project, .tide/state) decides if sign blocks on the human
(strict) or the orchestrator stamps it synchronously (loose).
"""
