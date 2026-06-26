"""tide.cannon.reality — M2 reality-rev: content hash over canon-covered paths.

The reality-rev is the second freshness axis: while cannon-rev tracks whether
CANON.md itself has changed, reality-rev tracks whether the *files CANON claims
to describe* have changed. When a covered file moves and an open arc's stamped
reality-rev disagrees with the current reality-rev, the gate trips STALE —
"code shipped, canon didn't."

``canon-covers:`` manifest
--------------------------
A project declares its covered paths in one of two places (checked in order):

1. **CANON.md preamble** — everything before the first ``## `` heading. A bare
   ``canon-covers:`` line starts the block; subsequent lines indented with
   whitespace OR prefixed with ``- `` are path globs relative to the project
   root. A non-indented non-blank line (or the first ``## `` heading) ends
   the block.

2. **.tide/state/canon-covers** — one glob per line; ``#``-led lines are
   comments and are stripped.

A project with no manifest degrades gracefully: :func:`reality_rev` returns
``None`` and no ``reality-rev:`` field is stamped into arc passports. This is
not an error — the project simply has no reality axis.

Hash mechanics
--------------
Matching files are sorted by relative path; the hash is sha256 over the
concatenation of ``"<rel_path>\\0<sha256_of_content>\\n"`` strings. This gives
a deterministic, content-defined rev that changes whenever any covered file is
added, removed, or modified, and is stable across machines.

In a git repo, ``git ls-files`` is used so only *tracked* files count
(untracked/ignored files are invisible to reality-rev). Outside git (e.g. test
fixtures without a repo), pathlib glob is the fallback.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from .. import fields, paths

# Match cannon.rev.REV_LEN for consistency.
REV_LEN = 12


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------

def parse_manifest(root: Path) -> Optional[List[str]]:
    """Return the list of path globs declared in the project's ``canon-covers:`` manifest.

    Checks (1) the ``canon-covers:`` block in CANON.md's preamble, then (2)
    ``.tide/state/canon-covers``. Returns ``None`` when neither is present so the
    caller can degrade gracefully.
    """
    canon = paths.canon_file(Path(root))
    if canon.is_file():
        globs = _parse_canon_text(canon.read_text(encoding="utf-8"))
        if globs is not None:
            return globs

    state_covers = paths.state_dir(Path(root)) / "canon-covers"
    if state_covers.is_file():
        lines = state_covers.read_text(encoding="utf-8").splitlines()
        globs = [
            ln.strip()
            for ln in lines
            if ln.strip() and not ln.strip().startswith("#")
        ]
        return globs if globs else None

    return None


def _parse_canon_text(text: str) -> Optional[List[str]]:
    """Extract ``canon-covers:`` globs from the preamble of *text* (before first ``## ``).

    A bare ``canon-covers:`` line starts the block. Subsequent lines that are
    indented (start with whitespace) or prefixed with ``- `` are glob patterns.
    A non-indented non-blank line or the first ``## `` heading ends the block.
    Returns ``None`` when the ``canon-covers:`` marker is absent.
    """
    in_covers = False
    globs: List[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            break  # end of preamble
        stripped = line.strip()
        if stripped == "canon-covers:":
            in_covers = True
            continue
        if in_covers:
            if stripped.startswith("- "):
                globs.append(stripped[2:].strip())
            elif line and line[0].isspace() and stripped:
                globs.append(stripped)
            elif stripped:
                # non-indented non-blank line → end of covers block
                in_covers = False
            # blank lines inside the block are allowed (ignored)

    return globs if globs else None


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------

def _is_git_repo(root: Path) -> bool:
    """True when *root* contains a ``.git`` entry (dir or worktree file)."""
    return (Path(root) / ".git").exists()


def _collect_git(root: Path, globs: List[str]) -> Dict[str, str]:
    """Collect git-tracked files matching *globs* via ``git ls-files``.

    Returns ``{relative_path: sha256_of_content}``.  Returns an empty dict on
    any subprocess error or when git is not installed.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--", *globs],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}

    file_hashes: Dict[str, str] = {}
    for rel in result.stdout.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        abs_path = Path(root) / rel
        if abs_path.is_file():
            content = abs_path.read_bytes()
            file_hashes[rel] = hashlib.sha256(content).hexdigest()
    return file_hashes


def _collect_fs(root: Path, globs: List[str]) -> Dict[str, str]:
    """Collect files matching *globs* via pathlib.glob (non-git fallback).

    Returns ``{relative_path: sha256_of_content}``.
    """
    file_hashes: Dict[str, str] = {}
    for pattern in globs:
        for abs_path in sorted(Path(root).glob(pattern)):
            if abs_path.is_file():
                rel = str(abs_path.relative_to(root))
                if rel not in file_hashes:
                    content = abs_path.read_bytes()
                    file_hashes[rel] = hashlib.sha256(content).hexdigest()
    return file_hashes


# ---------------------------------------------------------------------------
# Reality-rev computation
# ---------------------------------------------------------------------------

def reality_rev(root: Path) -> Optional[str]:
    """Return the reality-rev for *root*: a content hash over all covered files.

    Returns ``None`` when no ``canon-covers:`` manifest exists — graceful
    degradation, never an error. Uses ``git ls-files`` in git repos; falls
    back to pathlib glob otherwise.

    An empty glob match (manifest present but no matching files) returns the
    sha256 of empty bytes — a stable "empty-tree" rev — so the rev is defined
    and can detect files being *added* to coverage.
    """
    globs = parse_manifest(Path(root))
    if globs is None:
        return None

    if _is_git_repo(Path(root)):
        file_hashes = _collect_git(Path(root), globs)
    else:
        file_hashes = _collect_fs(Path(root), globs)

    if not file_hashes:
        return hashlib.sha256(b"").hexdigest()[:REV_LEN]

    digest = hashlib.sha256()
    for rel_path, content_hash in sorted(file_hashes.items()):
        digest.update("{0}\0{1}\n".format(rel_path, content_hash).encode("utf-8"))
    return digest.hexdigest()[:REV_LEN]


# ---------------------------------------------------------------------------
# Passport stamp
# ---------------------------------------------------------------------------

def stamp_reality_rev(passport_doc: Path, root: Path) -> Optional[str]:
    """Stamp the current ``reality-rev`` into *passport_doc* and return it.

    *passport_doc* is the actual passport file path (``arc.md`` or
    ``<slug>-goal.md``), not the entry dir.  This avoids importing
    ``arc.stream`` here and keeps the module cycle-free.

    A no-op (returns ``None``) when the project has no ``canon-covers:``
    manifest.  When a manifest exists, writes ``reality-rev: <rev>`` via
    :func:`tide.fields.set_field` and returns the rev.
    """
    rr = reality_rev(Path(root))
    if rr is not None:
        fields.set_field(Path(passport_doc), "reality-rev", rr)
    return rr
