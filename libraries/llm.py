"""llm.py - the one call to the Anthropic Messages API that `repo commit` makes.

Replaces aicommit's curl + jq subprocess with stdlib urllib: JSON encoding and
escaping come for free (the diff is full of quotes, newlines, backslashes -- the
exact thing the bash version hand-escaped), and the runtime needs no curl/jq.

AUTH MODEL (unchanged from the standardized aicommit)
  No native `claude` binary, no hypervisor. The key is read from the environment
  at RUNTIME -- $ANTHROPIC_API, falling back to the conventional $ANTHROPIC_API_KEY
  -- and sent as the x-api-key header. Nothing is ever baked into the binary.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from checks import die

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def api_url() -> str:
    """The Messages endpoint. $KAREN_API_URL overrides it -- useful for an API
    gateway/proxy, and for tests that point at a local stub. Defaults to the real one."""
    return os.environ.get("KAREN_API_URL", "").strip() or API_URL

# The system prompt pins haiku to a pure one-line generator. message.extract_subject
# is the SECONDARY net for when it ignores this on a large diff.
SYSTEM_PROMPT = (
    "You are a git commit message generator. You receive a staged diff and output "
    "EXACTLY ONE line: the commit subject. Imperative mood, 72 characters or fewer, "
    "no trailing period, no surrounding quotes, no backticks, no emojis, no preamble, "
    "no explanation, no leading label. Output nothing except that single subject line."
)
USER_PREAMBLE = "Write the commit subject line for the staged changes below."

# `karen version` with no part asks the model to decide the semver bump from the
# commits/diff since the last tag. It must answer with ONE bare word so the caller
# can map it straight onto version.PARTS.
BUMP_SYSTEM_PROMPT = (
    "You decide the Semantic Versioning bump for a release. You receive the commit "
    "log and diff since the last release tag. Reply with EXACTLY ONE word, lowercase, "
    "nothing else: 'major' for incompatible/breaking API changes, 'minor' for "
    "backwards-compatible new features, 'patch' for backwards-compatible bug fixes or "
    "internal changes. When unsure, prefer the smaller bump. Output only that one word."
)
BUMP_PREAMBLE = "Decide the semver bump for the changes since the last release below."


def api_key() -> str:
    """The key from $ANTHROPIC_API or $ANTHROPIC_API_KEY, or '' if neither is set."""
    return os.environ.get("ANTHROPIC_API") or os.environ.get("ANTHROPIC_API_KEY") or ""


def require_api_key() -> str:
    key = api_key()
    if not key:
        die("$ANTHROPIC_API is not set (export it in ~/.bashrc).")
    return key


def _call(system: str, user: str, *, model: str, max_tokens: int,
          timeout: float) -> str:
    """One Messages-API round-trip: send `system`/`user`, return the concatenated
    text content. An HTTP/network error or a content-less response returns '' so
    every caller's empty-guard handles failure uniformly. The key is read from the
    env (require_api_key) and sent as x-api-key; nothing is baked in."""
    key = require_api_key()
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")

    req = urllib.request.Request(
        api_url(),
        data=body,
        method="POST",
        headers={
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return ""

    parts = [
        block.get("text", "")
        for block in payload.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "".join(parts)


def generate_subject(diff: str, *, model: str, max_tokens: int = 64,
                     timeout: float = 30.0) -> str:
    """Ask `model` for a commit subject for `diff`. Returns the model's RAW text
    reply (message.extract_subject cleans it)."""
    return _call(SYSTEM_PROMPT, f"{USER_PREAMBLE}\n\n{diff}",
                 model=model, max_tokens=max_tokens, timeout=timeout)


def suggest_bump(changes: str, *, model: str, max_tokens: int = 16,
                 timeout: float = 30.0) -> str:
    """Ask `model` which semver part to bump given `changes` (the log + diff since
    the last tag). Returns the RAW reply; version_command maps it onto a part and
    falls back on an unrecognisable answer."""
    return _call(BUMP_SYSTEM_PROMPT, f"{BUMP_PREAMBLE}\n\n{changes}",
                 model=model, max_tokens=max_tokens, timeout=timeout)
