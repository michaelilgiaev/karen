"""commit_command.py - `karen commit`: the AI-written commit (was aicommit / llmcommit).

A drop-in replacement for `git commit -m "<message>"`: it asks the cheap Claude
haiku model for ONE commit subject line for the ALREADY-STAGED diff and commits
with it. It does NOT stage anything -- `git add` yourself first, exactly like a
plain `git commit -m`. With nothing staged it is a clean no-op.

Orchestration only: checks -> git_io (read diff) -> llm (ask) -> message (clean) ->
git_io (commit). The two retries mirror aicommit: on a big diff haiku may emit a
preamble, so if the cleaned subject is empty we ask once more.
"""

from __future__ import annotations

import sys

import checks
import configuration
import git_io
import llm
import message

_RETRIES = 2


def run() -> int:
    """Commit staged changes with an AI subject. Returns a process exit code."""
    checks.require_inside_work_tree()

    # Do NOT stage. Commit only what is already staged; a clean no-op otherwise,
    # exactly like a bare `git commit`.
    if not git_io.has_staged_changes():
        print("Nothing staged to commit.")
        return 0

    llm.require_api_key()                       # fail early + clearly if unset
    diff = git_io.staged_diff()
    model = configuration.model()

    subject = ""
    for _ in range(_RETRIES):
        reply = llm.generate_subject(diff, model=model)
        subject = message.extract_subject(reply)
        if subject:
            break

    if not subject:
        print(
            "karen: could not generate a clean message (is $ANTHROPIC_API valid?).",
            file=sys.stderr,
        )
        return 1

    git_io.commit(subject)
    return 0
