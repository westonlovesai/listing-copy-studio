"""
history.py
----------
A local, append-only log of every single-product generation, so a good
result is never lost just because you navigated away or closed the tab.

Kept deliberately simple: one JSON file, a capped length, newest first.
Batch runs are NOT logged here (they'd flood the history with dozens of
entries per click) - the CSV download is the batch "memory".
"""

import json
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path(__file__).parent / "history.json"
MAX_ENTRIES = 100


def append_entry(entry: dict) -> None:
    """Add one generation to the front of the history, trimmed to MAX_ENTRIES."""
    # The real timestamp is spread LAST so it always wins, even if the caller's
    # entry dict happens to already contain a (stale) "timestamp" key.
    entry = {**entry, "timestamp": datetime.now().isoformat(timespec="seconds")}
    history = load_history(limit=MAX_ENTRIES - 1)
    history.insert(0, entry)
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")


def load_history(limit: int = MAX_ENTRIES) -> list[dict]:
    """Return past generations, most recent first."""
    if not HISTORY_FILE.exists():
        return []
    try:
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return history[:limit]


def clear_history() -> None:
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
