"""tide.slug — slugify + ``__…__``-tolerant reference matching.

Ported from the arcs bash ``slugify`` (load-bearing — get it subtly wrong and
dir names diverge between create and lookup):

    lowercase → spaces / ``/`` / ``_`` to ``-`` → drop non ``[a-z0-9-]`` →
    collapse repeated ``-`` → trim leading/trailing ``-``.

References (the ``<old>`` in ``arc supersede``, a slug typed by the agent) may
arrive wrapped in the closed-marker ``__…__``; the matcher strips that before
comparing. Entry dir names carry a ``NN-`` prefix, an optional goal ``@`` mark,
and the closed ``__…__`` wrapper — :func:`entry_slug` peels all of that off so a
bare slug can be matched against on-disk entries.
"""

from __future__ import annotations

import re

_NON_SLUG = re.compile(r"[^a-z0-9-]")
_DASHES = re.compile(r"-+")
# NN- prefix (2+ digits past 99), optional goal '@' marker.
_ENTRY = re.compile(r"^(?P<num>\d{2,})-(?P<goal>@)?(?P<slug>.*)$")


def slugify(text: str) -> str:
    """Turn arbitrary text into a glob-safe kebab slug (arcs-compatible)."""
    s = (text or "").lower()
    s = s.replace(" ", "-").replace("/", "-").replace("_", "-")
    s = _NON_SLUG.sub("", s)
    s = _DASHES.sub("-", s)
    return s.strip("-")


def strip_marker(ref: str) -> str:
    """Remove a surrounding closed-marker ``__…__`` from a ref (one layer)."""
    r = ref or ""
    if r.startswith("__"):
        r = r[2:]
    if r.endswith("__"):
        r = r[:-2]
    return r


def normalize_ref(ref: str) -> str:
    """Canonicalise a user ref: strip ``__…__`` then slugify."""
    return slugify(strip_marker(ref))


def entry_slug(name: str) -> str:
    """Bare slug of an on-disk entry name.

    Handles open ``NN-slug`` / ``NN-@slug`` and closed ``__NN-slug__`` /
    ``__NN-@slug__``; returns just the ``slug`` part. A name without an
    ``NN-`` prefix falls back to a marker-stripped slugify.
    """
    bare = strip_marker((name or "").rstrip("/"))
    m = _ENTRY.match(bare)
    if m:
        return m.group("slug")
    return slugify(bare)


def is_goal_entry(name: str) -> bool:
    """True when an entry dir name marks a goal (``NN-@slug`` / ``__NN-@slug__``)."""
    bare = strip_marker((name or "").rstrip("/"))
    m = _ENTRY.match(bare)
    return bool(m and m.group("goal"))


def is_closed_entry(name: str) -> bool:
    """True when an entry dir name is wrapped in the closed marker ``__…__``."""
    n = (name or "").rstrip("/")
    return n.startswith("__") and n.endswith("__")


def ref_matches(ref: str, entry_name: str) -> bool:
    """True when bare *ref* names *entry_name* (both ``__…__``-tolerant)."""
    return normalize_ref(ref) == entry_slug(entry_name)
