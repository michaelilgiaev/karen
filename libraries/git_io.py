"""git_io.py - thin, testable wrappers over the git plumbing `repo` needs.

Every git shell-out lives here so the command modules (message/version) stay pure
logic and the tests can drive git through ONE surface. Each wrapper returns data
(or raises RepoError via die); none print. Mirrors qvm's split of IO away from logic.
"""

from __future__ import annotations

import subprocess

from checks import die

# How much of the staged diff we feed the model. The old aicommit capped the raw
# diff at 6000 bytes after a --stat header; keep that -- haiku does not need more to
# write one subject line, and a huge body only invites a reasoning preamble.
_DIFF_BYTES = 6000


def _git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run `git <args>` capturing text output. With check=True a non-zero exit dies."""
    res = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        die(f"git {' '.join(args)} failed: {res.stderr.strip() or res.stdout.strip()}")
    return res


def has_staged_changes() -> bool:
    """True when something is staged (the only thing `repo commit` ever commits).

    Mirrors `git diff --cached --quiet`: exit 1 means there IS a staged change.
    """
    return _git("diff", "--cached", "--quiet").returncode != 0


def staged_diff() -> str:
    """The staged diff, shaped exactly as the old aicommit fed it: a `--stat`
    summary, a separator, then the first _DIFF_BYTES of the full cached diff."""
    stat = _git("--no-pager", "diff", "--cached", "--stat").stdout
    body = _git("--no-pager", "diff", "--cached").stdout
    return f"{stat}\n---\n{body[:_DIFF_BYTES]}"


def commit(message: str) -> None:
    """Commit the ALREADY-staged changes with `message`. Dies on a git failure."""
    _git("commit", "-m", message, check=True)


def changes_since(ref: str) -> str:
    """The commit log + diff since `ref` (a tag), shaped for the bump model: the
    one-line subjects, a --stat, a separator, then the first _DIFF_BYTES of the diff.
    An empty `ref` means "since the start of history" (no previous release tag), so
    the whole history is summarised. Returns '' when there is nothing new since ref."""
    rangespec = f"{ref}..HEAD" if ref else "HEAD"
    log = _git("--no-pager", "log", "--pretty=format:- %s", rangespec).stdout
    stat = _git("--no-pager", "diff", "--stat", rangespec).stdout
    body = _git("--no-pager", "diff", rangespec).stdout
    if not (log.strip() or body.strip()):
        return ""
    return f"Commits:\n{log}\n\nFiles:\n{stat}\n---\n{body[:_DIFF_BYTES]}"


def list_version_tags() -> list[str]:
    """Every tag that looks like a semver release tag (`v1.2.3`), newest-commit first.

    We sort by tag crev-date via `git tag --sort`, but the CALLER decides the
    latest by parsing versions (tag date is not version order); this just returns
    the candidate tag names.
    """
    out = _git("tag", "--list", "v*").stdout
    return [t for t in (line.strip() for line in out.splitlines()) if t]


def tag_exists(name: str) -> bool:
    return name in set(list_version_tags()) or bool(
        _git("rev-parse", "--verify", "--quiet", f"refs/tags/{name}").stdout.strip()
    )


def create_annotated_tag(name: str, message: str) -> None:
    """Create an annotated tag `name` with `message`. Dies if it already exists."""
    _git("tag", "-a", name, "-m", message, check=True)


def head_has_commits() -> bool:
    """True once the repo has at least one commit (a fresh repo has no HEAD)."""
    return _git("rev-parse", "--verify", "--quiet", "HEAD").returncode == 0
