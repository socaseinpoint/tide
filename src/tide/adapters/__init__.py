"""tide.adapters — the pluggable terminal-adapter registry.

One ABC (:class:`tide.adapters.base.TerminalAdapter`), two shipped
implementations — ``orca`` (DEFAULT, drives Orca via osascript) and ``tmux``
(swappable fallback) — and a tiny name→adapter registry. The menu / handoff ask
:func:`get_adapter` for an adapter; an unknown name raises a clear error that
*lists the available ones*. The chosen adapter can be pinned in the project
``.claude/settings.json`` under ``terminal_adapter`` (resolved by
:func:`resolve_from_settings`); absent ⇒ the default.

Keeping the registry here (not in ``base``) lets ``base`` stay dependency-free and
each adapter import only ``base``.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Type

from ..arc.stream import StreamError
from .base import SpawnResult, TerminalAdapter, safe_title
from .orca import OrcaAdapter
from .tmux import TmuxAdapter

DEFAULT_ADAPTER = "orca"
SETTINGS_KEY = "terminal_adapter"

# name → adapter class. Insertion order is the "available" listing order.
_REGISTRY: Dict[str, Type[TerminalAdapter]] = {
    "orca": OrcaAdapter,
    "tmux": TmuxAdapter,
}


class AdapterError(StreamError):
    """An unknown / unresolvable terminal adapter.

    Subclasses :class:`tide.arc.stream.StreamError` so ``cli.main`` catches it on
    the same ``except`` arm (prints ``tide: …``, exits nonzero).
    """


def available_adapters() -> List[str]:
    """The registered adapter names, in listing order (``orca`` first)."""
    return list(_REGISTRY.keys())


def get_adapter(name: Optional[str] = None) -> TerminalAdapter:
    """Resolve *name* to a fresh adapter instance; default ``orca`` when None/blank.

    An unknown name raises :class:`AdapterError` naming the available adapters, so
    a typo fails loud rather than silently falling back.
    """
    key = (name or DEFAULT_ADAPTER).strip().lower()
    cls = _REGISTRY.get(key)
    if cls is None:
        raise AdapterError(
            "unknown terminal adapter {0!r} — available: {1}".format(
                name, ", ".join(available_adapters())
            )
        )
    return cls()


def resolve_from_settings(settings: Optional[dict]) -> TerminalAdapter:
    """Resolve the adapter pinned in a settings dict (``terminal_adapter``) or default."""
    name = None
    if isinstance(settings, dict):
        value = settings.get(SETTINGS_KEY)
        if isinstance(value, str) and value.strip():
            name = value
    return get_adapter(name)


__all__ = [
    "AdapterError",
    "DEFAULT_ADAPTER",
    "SETTINGS_KEY",
    "SpawnResult",
    "TerminalAdapter",
    "available_adapters",
    "get_adapter",
    "resolve_from_settings",
    "safe_title",
]
