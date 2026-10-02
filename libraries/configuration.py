"""configuration.py - which Anthropic model karen asks.

There is nothing to persist: the model is the built-in default unless $KAREN_MODEL
overrides it for a run. Auth is separate and never stored (see llm.py).
"""

from __future__ import annotations

import os

# Cheap, fast, one subject line -- the same model the old aicommit pinned.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def model() -> str:
    """The effective model: $KAREN_MODEL if set, else the built-in default."""
    return os.environ.get("KAREN_MODEL", "").strip() or DEFAULT_MODEL
