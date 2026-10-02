"""version_command.py - `karen version`: semver bump + annotated git tag.

This is the "versioncommit" piece, and it TAKES THE WHEEL: bare `karen version`
asks the model which part to bump from the commits/diff since the last release
tag (the same LLM-driven approach as `karen commit`), then tags it. You can still
force a part -- `karen version minor` -- but you do not have to.

  karen version [major|minor|patch] [--file PATH]

It reads the latest `vX.Y.Z` tag and bumps from it (lower parts reset to 0); with
no tag it starts from v0.0.0, so a first `patch` yields v0.0.1. --file PATH also
rewrites a version string in PATH before tagging.

The tag is created LOCALLY and nothing is pushed -- publish it yourself with
`git push origin master --tags`.

Orchestration only: version.py is the pure logic, git_io.py does the git, llm.py +
message.py decide the bump.
"""

from __future__ import annotations

import sys

import checks
import configuration
import git_io
import llm
import message
import version
from checks import die

_RETRIES = 2


def _rewrite_version_file(path: str, new: "version.Version") -> None:
    """Replace the first semver found in `path` with `new`. Dies if the file has no
    parseable version line, so a typo'd --file never silently tags without bumping."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        die(f"cannot read --file {path}: {exc}")

    for i, line in enumerate(lines):
        if version.parse(line) is not None:        # a bare `X.Y.Z` / `vX.Y.Z` line
            prefix = "v" if line.strip().startswith("v") else ""
            lines[i] = f"{prefix}{new}\n"
            break
    else:
        die(f"--file {path}: no version line (a bare X.Y.Z) found to bump")

    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)


def _decide_bump(current: "version.Version | None") -> str:
    """Ask the model which part to bump from the changes since the last tag. Dies
    cleanly if there is nothing to release or the model cannot be reached."""
    llm.require_api_key()                       # fail early + clearly if unset
    ref = current.tag if current else ""
    changes = git_io.changes_since(ref)
    if not changes:
        die("nothing to release since the last tag (no new commits).")

    model = configuration.model()
    for _ in range(_RETRIES):
        part = message.extract_bump(llm.suggest_bump(changes, model=model))
        if part:
            return part
    die("could not decide the version bump (is $ANTHROPIC_API valid?). "
        "Pass a part explicitly: karen version patch|minor|major.")


def run(part: str = "", *, version_file: str = "") -> int:
    """Bump `part` (model-decided when empty) and tag the result LOCALLY. Returns an
    exit code. Nothing is pushed -- publish with `git push origin master --tags`."""
    if part and part not in version.PARTS:
        print(
            f"karen version: part must be one of {', '.join(version.PARTS)} (got '{part}').",
            file=sys.stderr,
        )
        return 2

    checks.require_inside_work_tree()

    tags = git_io.list_version_tags()
    current = version.latest(tags)

    decided_by_model = not part
    if decided_by_model:
        part = _decide_bump(current)

    new = current.bump(part) if current else version.Version(0, 0, 0).bump(part)

    if git_io.tag_exists(new.tag):
        die(f"tag {new.tag} already exists.")

    if version_file:
        _rewrite_version_file(version_file, new)

    git_io.create_annotated_tag(new.tag, f"Release {new.tag}")
    how = f"{part}, chosen by the model" if decided_by_model else part
    shown_current = current.tag if current else "(none)"
    print(f"karen version: tagged {new.tag} ({how}, was {shown_current}).")
    print("               push it with: git push origin master --tags")
    return 0
