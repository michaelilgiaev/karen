"""message.py - turn a model reply into ONE clean commit subject line.

This is the logic the old aicommit implemented as a fragile pipeline of `sed`,
`grep`, backtick strips and a bash `case` reject list inside a triple-escaped
heredoc. Porting it to Python is the whole point of the overhaul: the exact
behaviour is preserved, but it is now readable and unit-tested instead of hiding
in the triple-escaped bash heredoc where a stray backslash silently broke it.

WHY THIS EXISTS
  haiku is pinned by a system prompt to emit ONE subject line, but on a LARGE
  diff it can still prepend a short reasoning preamble with the real subject as
  the LAST line, or fence its answer. So we:
    * take the LAST non-empty line (not the first),
    * drop fence lines first,
    * strip wrapping backticks/quotes and a trailing period,
    * reject obvious non-subjects (chatter, list items, lead-ins, prose),
  and the caller retries once if what survives is empty.
"""

from __future__ import annotations

import re

# A fence line: ``` optionally followed by a language tag, nothing else.
_FENCE_RE = re.compile(r"^```[A-Za-z0-9]*$")

# Reject shapes that are NOT a subject. Ported verbatim from aicommit's bash `case`:
#   * a reasoning / first-person opener,
#   * an acknowledgement (what a model emits when something made it keep talking),
# all anchored at the START so a legitimate subject ("This fixes ...") is only
# caught when it literally opens with one of these lead-ins.
_LEADINS = (
    "Looking at ", "Here ", "I ", "Let me ", "Sure", "Okay", "Based on ",
    "The staged ", "The changes ", "This ",
)
_ACKS = (
    "Done", "Perfect", "Got it", "Great", "Understood", "Certainly", "Of course",
)

# The length cap. aicommit asked for <=72 but only REJECTED past 100 (a real
# subject a little over 72 is fine; prose is far longer). Keep that threshold.
_MAX_LEN = 100


def _strip_wrappers(line: str) -> str:
    """Strip a single pair of wrapping backticks or double-quotes, then a trailing
    period -- the three cosmetic things haiku adds around an otherwise clean line."""
    for q in ("`", '"'):
        if len(line) >= 2 and line.startswith(q) and line.endswith(q):
            line = line[1:-1]
    return line[:-1] if line.endswith(".") else line


def _is_rejected(line: str) -> bool:
    """True when `line` is chatter/prose/a list item rather than a subject."""
    if line.endswith(":"):                      # lead-in to a list that followed
        return True
    if line.startswith(_LEADINS) or line.startswith(_ACKS):
        return True
    if line[:2] in ("- ", "* ", "+ "):          # a single bullet, not the whole change
        return True
    if not re.search(r"[A-Za-z0-9]", line):     # punctuation debris (lone fence/dash)
        return True
    if len(line) > _MAX_LEN:                     # prose, not a subject
        return True
    return False


def extract_subject(reply: str) -> str:
    """Return a clean commit subject from the model's raw `reply`, or '' if none.

    Takes the LAST non-empty, non-fence line (both ends trimmed), strips wrappers
    and a trailing period, and returns '' when the result is rejected -- the signal
    the caller uses to retry once.
    """
    candidate = ""
    for raw in reply.splitlines():
        line = raw.strip()
        if not line or _FENCE_RE.match(line):
            continue
        candidate = line                        # keep the last survivor
    if not candidate:
        return ""
    candidate = _strip_wrappers(candidate)
    return "" if _is_rejected(candidate) else candidate


def extract_bump(reply: str) -> str:
    """Map the bump model's raw `reply` onto 'major'/'minor'/'patch', or '' if none
    is found. The model is told to answer with one bare word, but we scan the whole
    reply case-insensitively for the FIRST of the three words so a stray wrapper or
    preamble ("Bump: minor") still resolves."""
    for word in re.findall(r"[a-z]+", reply.lower()):
        if word in ("major", "minor", "patch"):
            return word
    return ""
