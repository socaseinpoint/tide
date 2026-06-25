# tide

**tide = simplified orchestration machine.** Pure CLI + markdown files.
Synchronous, human-driven, **no autonomy** — no web surface, no Telegram, no
background daemon. One `tide` binary with namespaced subcommands. tide dogfoods
itself (it is led as a tide project).

`tide init` unfolds the machine in a directory → that dir becomes the
**control-home / roster**, the point from which the human leads all projects.
Projects live anywhere on disk; tide is where they're led from.

> Greenfield Python build, stdlib-only runtime. All command groups are
> implemented (init · roster · arc · cannon · contract · candidate · status ·
> strictness · hooks · launcher). Requires **Python ≥ 3.12** — the system
> `python3` may be older, so install under a 3.12 interpreter (pipx or a venv).

## Install

```bash
python3.12 -m pip install -e .            # runtime (stdlib only)
python3.12 -m pip install -e '.[test]'    # + pytest for the test suite
tide --version
# or, without installing the console script:
python3.12 -m tide --version
```

## Human playbook (brief)

- `tide init` — unfold a control-home (roster + dogfood `.tide/`).
- `tide roster add|rm|ls` — register the projects you lead.
- `tide` — menu: pick N projects → launch a seeded **orchestrator** session.
- `tide <project> [<arc>]` — jump straight into a project/arc.
- `tide status [--all]` — the stream board. Flags **unmerged deltas** (any
  closed arc whose cannon-delta isn't merged) and **drift on open arcs** (an
  active arc stamped at an older cannon-rev than current). Closed arcs keep
  their original stamp by design and are not drift-flagged.
- `tide strictness [strict|loose]` — per-project dispatch dial.

The human steers; the **agent runs the module CLI** (`tide arc …`,
`tide cannon …`, `tide contract …`, `tide candidate …`). You never type those.

## Two roles

| | **orchestrator** | **worker** |
|---|---|---|
| scope | cross-project session | one arc |
| owns | roster, arc create/select, contracts, **cannon merge**, candidate **promote**, handoff | produce arc output, surface candidates, **propose cannon-delta** |
| never | does project work directly | merges cannon, touches another arc |

The worker is a subagent inside the orchestrator session. Role is carried by the
`TIDE_ROLE` env var (`orchestrator` | `worker`); the launcher sets it.

## build conventions

All later units MUST follow these. They are the contract this scaffold establishes.

### 1. Handler pattern (CLI wiring)

- **One binary, argparse, stdlib only.** No `click`, no runtime deps.
- Each module owns its subcommand group and exposes a
  **`register(subparsers)`** that adds its parser(s) and sets a thin handler via
  `parser.set_defaults(func=<handler>)`.
- **Handlers stay thin** — argument unpacking + I/O only. The real logic lives in
  **plain, argparse-free module functions** so it is unit-testable without the CLI.
  (e.g. `slugify(text)`, `next_num(dir)`, `merge_delta(arc, cannon)`.)
- `cli.py` only *wires* groups; it never contains domain logic. Today it
  registers **stubs** (`_register_*` with `# TODO(U#)` tags). When a unit lands,
  replace its `_register_*` body with `from .<module> import register; register(subparsers)`.
- A handler returns an `int` exit code (or `None` → 0).

### 2. Role gating

- `cli.current_role()` reads `$TIDE_ROLE` (default `worker` — least privilege).
- Orchestrator-only operations (`cannon merge`, `candidate promote`) MUST call
  `cli.require_orchestrator("<action>")` first; it raises a nonzero `SystemExit`
  with a clear message unless `TIDE_ROLE=orchestrator`.

### 3. Where state lives

Per project, everything is under **`<project>/.tide/`** with three siblings:

| dir | holds |
|---|---|
| `cannon/` | `CANON.md` (living IS) + `config` (`lang=en`); durable truth, notes/changelog/goals folded in |
| `arcs/` | the numbered work stream `NN-<slug>/` (arc) and `NN-@<slug>/` (goal); `arcs/candidates/` is a separate backlog |
| `state/` | `strictness` (strict\|loose, default strict) + cannon-rev stamps + contract index |

The control-home (where `tide init` ran) adds a top-level **`roster.md`**
(`name | path` lines) and its own dogfood `.tide/`.

### 4. On-disk format invariants (don't get these subtly wrong)

- **Frontmatter** = first line matching `^key:`; value = everything after
  `key:\s*`. `prev:` is a **read-only alias** of `supersedes:`.
- **Closed entry** = wrapped dir `__NN-<slug>__` **AND** `status: done` in the
  doc — both must agree (dual marking).
- **Numbering**: `next_num()` counts BOTH `NN-*/` and `__NN-*__/`, **never
  reuses** (closing renames, never frees a number). **Candidates have a SEPARATE
  counter.** Goal sub-arcs use their own local `01,02…` stream.
- **cannon-rev** = short sha256 of **`CANON.md` only** (the truth) — *not* the
  whole `cannon/` dir, so note/changelog tweaks don't spam drift.
- **Encapsulation**: an arc is `input/` → `workspace/` (disposable) → `output/`;
  outside reads **`output/` only**. The merge into `CANON.md` is the single
  serialization point and happens only in the live orchestrator session.

## build order (13 units)

U1 core · U2 cannon (store/rev/merge) · U3 arc stream · U4 candidates ·
U5 strictness + roster · U6 contract + ask/answer · U7 sync engine ·
U8 board render · U9 init_home + CLI wiring · U10 hooks · U11 launcher +
adapters · U12 prompts/rules + /tide-handoff skill · U13 e2e smoke + dogfood.

## Tests

```bash
cd /Users/socaseinpoint/Documents/projects/tide
python3 -m pytest tests/ -q
```

The suite is cumulative and must stay green as units land.
