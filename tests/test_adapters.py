"""U11 unit — adapters: registry (default orca), tmux/orca dry-run, unknown raises."""

from __future__ import annotations

import pytest

from tide import adapters
from tide.adapters import base
from tide.adapters.orca import OrcaAdapter
from tide.adapters.tmux import TmuxAdapter


# --- registry --------------------------------------------------------------

def test_get_adapter_default_is_orca():
    a = adapters.get_adapter()
    assert isinstance(a, OrcaAdapter)
    assert a.name == "orca"


def test_get_adapter_by_name():
    assert isinstance(adapters.get_adapter("tmux"), TmuxAdapter)
    assert isinstance(adapters.get_adapter("ORCA"), OrcaAdapter)  # case-insensitive


def test_unknown_adapter_raises_listing_available():
    with pytest.raises(adapters.AdapterError) as exc:
        adapters.get_adapter("kitty")
    msg = str(exc.value)
    assert "kitty" in msg
    # the error lists what IS available
    assert "orca" in msg and "tmux" in msg


def test_available_adapters_lists_both_orca_first():
    assert adapters.available_adapters() == ["orca", "tmux"]


def test_resolve_from_settings_reads_terminal_adapter_key():
    assert isinstance(adapters.resolve_from_settings({"terminal_adapter": "tmux"}), TmuxAdapter)
    # absent / blank / non-dict → default orca
    assert isinstance(adapters.resolve_from_settings({}), OrcaAdapter)
    assert isinstance(adapters.resolve_from_settings({"terminal_adapter": "  "}), OrcaAdapter)
    assert isinstance(adapters.resolve_from_settings(None), OrcaAdapter)


# --- tmux dry-run (the build-blueprint's required test) --------------------

def test_tmux_spawn_dry_run_builds_new_window_without_executing():
    a = TmuxAdapter()
    res = a.spawn(seed="SEED-BODY", cwd="/p/focus", title="tide-focus", dry_run=True)
    assert res.ok is True
    assert "dry-run" in res.detail.lower()
    # first command is the new-window invocation, scoped to cwd + title
    new_window = res.commands[0]
    assert new_window[:2] == ["tmux", "new-window"]
    assert "-c" in new_window and "/p/focus" in new_window
    assert "-n" in new_window and "tide-focus" in new_window
    assert base.SESSION_PROGRAM in new_window
    # second command delivers the seed into the window
    send = res.commands[1]
    assert send[:3] == ["tmux", "send-keys", "-t"]
    assert "SEED-BODY" in send


def test_tmux_build_commands_is_pure():
    a = TmuxAdapter()
    cmds = a.build_commands(seed="s", cwd="/c", title="t")
    assert len(cmds) == 2
    assert cmds[0][0] == "tmux"


# --- orca dry-run ----------------------------------------------------------

def test_orca_spawn_dry_run_builds_osascript_without_executing():
    a = OrcaAdapter()
    res = a.spawn(seed="SEED", cwd="/p/x", title="tide-x", dry_run=True)
    assert res.ok is True
    cmd = res.commands[0]
    assert cmd[0] == "osascript" and cmd[1] == "-e"
    script = cmd[2]
    assert "Orca" in script
    assert "/p/x" in script
    assert base.SESSION_PROGRAM in script


# --- SpawnResult / helpers -------------------------------------------------

def test_spawn_result_defaults():
    r = base.SpawnResult(ok=True)
    assert r.ref is None and r.detail == "" and r.commands == []


def test_safe_title_is_never_empty():
    assert base.safe_title("") == "tide"
    assert base.safe_title("a b/c") == "a-b-c"
