"""tide.adapters.tmux — the swappable fallback adapter (proves pluggability).

tmux is the headless-friendly alternative to the default Orca adapter: it needs
no Accessibility grant and no GUI, so it doubles as the "interface is genuinely
pluggable" proof and as a usable fallback on a server. It opens a new window in
the running tmux server, ``cd``s into the project, starts a fresh Claude session,
and types the seed into it.

Two commands are built (and, on a real spawn, executed in order):

1. ``tmux new-window -c <cwd> -n <title> <SESSION_PROGRAM>`` — the new window.
2. ``tmux send-keys -t <title> <seed> Enter`` — deliver the seed as the opening
   prompt.

The dry-run path returns both on :attr:`SpawnResult.commands` WITHOUT executing —
that is the unit test the build-blueprint asks for.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import List

from .base import SESSION_PROGRAM, SpawnResult, TerminalAdapter, safe_title


class TmuxAdapter(TerminalAdapter):
    """Fallback adapter: ``tmux new-window`` + ``send-keys`` the seed."""

    name = "tmux"

    def build_commands(self, *, seed: str, cwd: str, title: str) -> List[List[str]]:
        """Build the (new-window, send-keys) command pair — pure, no execution."""
        window = safe_title(title)
        new_window = [
            "tmux", "new-window",
            "-c", cwd,
            "-n", window,
            SESSION_PROGRAM,
        ]
        send_seed = ["tmux", "send-keys", "-t", window, seed, "Enter"]
        return [new_window, send_seed]

    def spawn(
        self,
        *,
        seed: str,
        cwd: str,
        title: str = "tide",
        dry_run: bool = False,
    ) -> SpawnResult:
        commands = self.build_commands(seed=seed, cwd=cwd, title=title)
        if dry_run:
            return SpawnResult(
                ok=True,
                ref=safe_title(title),
                detail="dry-run (tmux not executed)",
                commands=commands,
            )

        if shutil.which("tmux") is None:
            return SpawnResult(
                ok=False,
                detail="tmux not found on PATH — install tmux or pick another adapter",
                commands=commands,
            )

        try:
            for cmd in commands:
                subprocess.run(cmd, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover
            return SpawnResult(
                ok=False,
                detail="tmux spawn failed: {0}".format(exc),
                commands=commands,
            )
        return SpawnResult(
            ok=True,
            ref=safe_title(title),
            detail="opened tmux window {0!r}".format(safe_title(title)),
            commands=commands,
        )
