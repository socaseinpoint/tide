# tide

**A simplified orchestration machine. Pure CLI + markdown — nothing else.**

One `tide` binary leads all your projects from a single control-home. No web
surface, no daemon, no autonomy: it's **synchronous and human-driven**. You steer
in plain words; an agent runs the commands. All state lives in plain markdown you
can `cat`, `grep`, and `diff` — not in a chat or a database.

→ **See the whole idea on one page: https://tide-tools.github.io/tide/**

---

## Install

Requires **Python ≥ 3.12** (the runtime is stdlib-only — no web deps).

**Homebrew** (recommended)

```bash
brew tap tide-tools/tide https://github.com/tide-tools/homebrew-tide
brew install tide-tools/tide/tide
tide --version
```

**From source**

```bash
git clone https://github.com/tide-tools/tide && cd tide
./install.sh        # puts tide on your PATH under a 3.12 interpreter
```

**pip**

```bash
python3.12 -m pip install "git+https://github.com/tide-tools/tide@v1.0.2"
```

Brew and pip installs **keep themselves current**: a session tells you when a
newer release exists, and `tide self-update` reinstalls it only after a
regression gate passes — never a downgrade, never interrupting running work, with
a rollback if something slips.

---

## What it's for

You lead several projects. Each needs context loaded, work scoped, and decisions
recorded — and the thread is easy to lose between sessions. tide is the **one
place you lead from**:

- **Plain text is the database.** Everything is markdown under
  `<project>/.tide/`. No server, no lock file — `git`, `grep`, `diff` just work.
- **You steer; the agent runs the verbs.** You talk in plain words; the session
  runs the CLI for you. You never memorize commands.
- **Truth has one home.** Work happens in a bounded *arc*, bound to a *contract*
  you sign, then folded into *canon* — the single place durable truth gathers.
- **No autonomy, by design.** Synchronous, human-driven, least-privilege. No
  background daemon quietly deciding things.
- **Composable, not a platform.** tide doesn't host your projects; they live
  wherever they live. It just holds the thread.

tide dogfoods itself — it's led as a tide project, in its own `.tide/`.

---

## Try it

```bash
mkdir ~/control && cd ~/control
tide init --name control      # unfold a control-home
tide onboarding               # a short guided first-project walkthrough — or skip it
```

Then just **talk**. Register a project, open a session over it, and say what you
want — *"ship onboarding: a 3-step walkthrough, no console errors."* The session
carves the arc, binds a contract you sign off on, dispatches the work, and folds
the result into canon. You approve; the plumbing stays hidden.

Want to watch the loop run on something real? `examples/tide-pool/` is a browser
game built end-to-end through three arcs — see its
[`SHOWCASE.md`](examples/tide-pool/SHOWCASE.md).

---

## Learn more

- **The pitch, in one page:** https://tide-tools.github.io/tide/
- **Hands-on in 5 minutes:** [QUICKSTART.md](QUICKSTART.md)
- **Every command:** `tide help`
- **Develop:** `python3.12 -m pytest -q` (the suite is cumulative and stays green)

Built like a small UNIX tool, on purpose. MIT licensed.
