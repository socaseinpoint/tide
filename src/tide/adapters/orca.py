"""tide.adapters.orca — the DEFAULT adapter, drives Orca via ``osascript``.

Orca Helper.app is the terminal the orchestrator already lives in on this
machine; this adapter (ported from the focus handoff skill's Orca control) opens
a NEW Orca terminal tab, ``cd``s into the project, starts a fresh Claude session,
and hands it the seed. It needs an Accessibility grant + Orca installed, so it
**degrades gracefully**: when ``osascript`` is missing or errors it returns
``ok=False`` with instructions instead of raising — the caller can then suggest
``--adapter tmux``.

The seed is persisted to a file (:func:`tide.adapters.base.persist_seed`) and the
typed command points the fresh session at it (a multi-KB pasted prompt is
unreliable to keystroke). The dry-run path builds the ``osascript`` command
WITHOUT writing or executing anything.
"""

from __future__ import annotations

import shutil
import subprocess

from .base import (
    SESSION_PROGRAM,
    SpawnResult,
    TerminalAdapter,
    persist_seed,
    safe_title,
)

# AppleScript: activate Orca, open a new tab (Cmd-T), then type the launch line.
# Kept as a template so the dry-run can show the exact script that would run.
_OSASCRIPT_TEMPLATE = """tell application "Orca" to activate
tell application "System Events"
    keystroke "t" using command down
    delay 0.4
    keystroke "cd {cwd} && {program}  # tide seed: {seed_file}"
    key code 36
end tell"""


class OrcaAdapter(TerminalAdapter):
    """Default adapter: ``osascript`` opens a new Orca tab and starts a session."""

    name = "orca"

    def build_script(self, *, cwd: str, seed_file: str) -> str:
        """Render the AppleScript that opens the tab and types the launch line."""
        return _OSASCRIPT_TEMPLATE.format(
            cwd=cwd, program=SESSION_PROGRAM, seed_file=seed_file
        )

    def spawn(
        self,
        *,
        seed: str,
        cwd: str,
        title: str = "tide",
        dry_run: bool = False,
    ) -> SpawnResult:
        if dry_run:
            # Show the script without writing a seed file or driving the UI.
            script = self.build_script(cwd=cwd, seed_file="<seed-file>")
            return SpawnResult(
                ok=True,
                ref=safe_title(title),
                detail="dry-run (osascript not executed)",
                commands=[["osascript", "-e", script]],
            )

        if shutil.which("osascript") is None:
            return SpawnResult(
                ok=False,
                detail=(
                    "osascript not found — Orca control needs macOS + an "
                    "Accessibility grant; try '--adapter tmux'"
                ),
            )

        seed_path = persist_seed(seed, title)
        script = self.build_script(cwd=cwd, seed_file=str(seed_path))
        try:
            subprocess.run(["osascript", "-e", script], check=True)
        except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover
            return SpawnResult(
                ok=False,
                detail=(
                    "Orca spawn failed ({0}); grant Accessibility to Orca or "
                    "use '--adapter tmux'. seed at {1}".format(exc, seed_path)
                ),
                commands=[["osascript", "-e", script]],
            )
        return SpawnResult(
            ok=True,
            ref=safe_title(title),
            detail="opened a new Orca tab (seed at {0})".format(seed_path),
            commands=[["osascript", "-e", script]],
        )
