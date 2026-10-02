"""command_line_interface.py - argument parsing, usage text, and the dispatch entry point.

karen is a repository manager: a single `karen` command whose subcommands each do
one git chore well. Today:

  * karen commit   -- commit the STAGED diff with an AI-written subject (the old
                      aicommit / "llmcommit").
  * karen version  -- bump semver and create an annotated git tag ("versioncommit").

This file only parses args and dispatches into the *_command modules; all the real
logic lives there (mirrors qvm's command_line_interface.py).
"""

from __future__ import annotations

import os
import sys

# Flat sibling imports: the modules live directly in libraries/ (no package), so the
# bare imports resolve against this dir once it is on sys.path. The launcher runs this
# flat by absolute path and does NOT cd -- the caller's CWD is preserved so git acts on
# the repository the user is standing in. Mirrors qvm's command_line_interface.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import commit_command  # noqa: E402  (after the sys.path bootstrap above)
import configuration  # noqa: E402  (for the default-model name in usage)
import version_command  # noqa: E402
from checks import RepoError  # noqa: E402

PROG = "karen"


def usage() -> str:
    return f"""\
{PROG} - a repository manager: one command for the git chores you repeat.

Run it inside a git repository. Each subcommand does one chore:

USAGE:
  {PROG} commit              Commit the ALREADY-STAGED diff with a commit subject
                             written by the cheap Claude haiku model. Does NOT stage
                             anything -- `git add` yourself first, exactly like a
                             plain `git commit -m`. With nothing staged it is a no-op.
  {PROG} version [part]      Bump semver and create an annotated git tag LOCALLY.
      [--file PATH]          With NO part the model decides it (major/minor/patch)
                             from the commits since the last tag; pass a part to
                             force it. Bumps from the latest vX.Y.Z tag, or v0.0.0 if
                             none. --file PATH also rewrites a version string in PATH
                             before tagging. Nothing is pushed -- publish it with
                             `git push origin master --tags`.
  {PROG} help                This text.

AUTH ($ANTHROPIC_API, read at RUNTIME -- never stored):
  karen calls the Anthropic Messages API directly and reads the key from
  $ANTHROPIC_API (falling back to $ANTHROPIC_API_KEY). Export it in ~/.bashrc:
      export ANTHROPIC_API="sk-ant-..."
  With no key set, karen refuses cleanly. No key is ever baked into the binary.

ENV OVERRIDES:
  KAREN_MODEL     override the Anthropic model (default {configuration.DEFAULT_MODEL}).
  KAREN_API_URL   override the Messages endpoint (an API gateway/proxy).

EXAMPLE:
  git add -p
  {PROG} commit
  {PROG} version              # the model picks the bump, then tags locally
  {PROG} version minor        # or force it
  git push origin master --tags   # publish the commit and the new tag"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "help"
    rest = argv[1:]

    try:
        if cmd == "commit":
            return commit_command.run()
        if cmd == "version":
            return _dispatch_version(rest)
        if cmd in ("help", "-h", "--help"):
            print(usage())
            return 0
        print(f"{PROG}: unknown subcommand: {cmd}\n", file=sys.stderr)
        print(usage(), file=sys.stderr)
        return 2
    except RepoError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def _dispatch_version(rest: list[str]) -> int:
    """Parse `version [part] [--file PATH]` and run it. A part is OPTIONAL -- with
    none, version_command asks the model to decide the bump."""
    part = ""
    version_file = ""
    i = 0
    while i < len(rest):
        token = rest[i]
        if token == "--file":
            if i + 1 >= len(rest):
                print(f"{PROG} version: --file needs a PATH.", file=sys.stderr)
                return 2
            version_file = rest[i + 1]
            i += 1
        elif token.startswith("--file="):
            version_file = token.split("=", 1)[1]
        elif token.startswith("--"):
            print(f"{PROG} version: unknown flag: {token}", file=sys.stderr)
            return 2
        elif not part:
            part = token
        i += 1

    return version_command.run(part, version_file=version_file)


# command_line_interface.py IS the CLI entry: main() lives here and the flat sibling
# imports load it by absolute path (no package). The frozen `karen` binary drives it
# through karen_main.py; this block also lets the file run directly as a script.
if __name__ == "__main__":
    sys.exit(main())
