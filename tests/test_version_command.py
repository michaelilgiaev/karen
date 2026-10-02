"""Tests for version_command.run -- the `karen version` orchestration, against
throwaway repos. Real git, tmp_path only.

A tag must point at a commit, so these use the `committed_repo` fixture (one commit,
HEAD exists). The invalid-part check does not reach git, so it uses a bare repo.

Two paths:
  * a FORCED part (`karen version minor`) -- never touches the model;
  * NO part (`karen version`) -- the model decides the bump. Those tests stub
    llm.suggest_bump so nothing hits the network, exactly like test_llm.py.
"""

from __future__ import annotations

import subprocess

import pytest

import version_command
from checks import RepoError


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)


def _new_commit(repo, name="feature.py"):
    """Add a fresh commit so there is something to release since the last tag --
    _decide_bump reads the commits/diff AFTER the tag and bails if there are none."""
    (repo / name).write_text("x = 1\n")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", f"Add {name}")


def _stub_bump(monkeypatch, word):
    """Make the model 'decide' `word`, with a key present so require_api_key passes.
    Patched on version_command.llm so run()'s _decide_bump picks it up."""
    monkeypatch.setenv("ANTHROPIC_API", "sk-ant-TEST")
    monkeypatch.setattr(version_command.llm, "suggest_bump",
                        lambda changes, *, model: word)


# --- forced part -----------------------------------------------------------

def test_first_tag_from_empty_repo(committed_repo, capsys):
    version_command.run("patch")
    tags = _git(committed_repo, "tag").stdout.split()
    assert tags == ["v0.0.1"]
    assert "v0.0.1" in capsys.readouterr().out


def test_bump_minor_from_existing_tag(committed_repo, capsys):
    _git(committed_repo, "tag", "-a", "v1.2.3", "-m", "Release v1.2.3")
    version_command.run("minor")
    assert "v1.3.0" in set(_git(committed_repo, "tag").stdout.split())


def test_invalid_part_returns_2(git_repo):
    assert version_command.run("banana") == 2


def test_duplicate_tag_raises(committed_repo, monkeypatch):
    # The guard is defensive: a normal bump ALWAYS lands above latest(), so it can
    # never collide on its own. To prove run() refuses a collision rather than
    # letting git error out mid-tag, force the one check it makes -- tag_exists on
    # the computed target -- to report the tag already present.
    _git(committed_repo, "tag", "-a", "v1.0.0", "-m", "Release v1.0.0")
    monkeypatch.setattr(version_command.git_io, "tag_exists", lambda name: True)
    with pytest.raises(RepoError):
        version_command.run("patch")
    # It bailed BEFORE creating anything: only the baseline tag exists.
    assert _git(committed_repo, "tag").stdout.split() == ["v1.0.0"]


def test_file_rewrite_bumps_in_tree(committed_repo):
    vf = committed_repo / "VERSION"
    vf.write_text("0.0.0\n")
    version_command.run("minor", version_file=str(vf))
    assert vf.read_text().strip() == "0.1.0"
    assert "v0.1.0" in set(_git(committed_repo, "tag").stdout.split())


def test_file_rewrite_preserves_v_prefix(committed_repo):
    # The version comes from the git TAG, not the file; the file is rewritten to
    # match, keeping its `v` prefix. Tag v1.0.0 so a patch bump yields v1.0.1.
    _git(committed_repo, "tag", "-a", "v1.0.0", "-m", "Release v1.0.0")
    vf = committed_repo / "VERSION"
    vf.write_text("v1.0.0\n")
    version_command.run("patch", version_file=str(vf))
    assert vf.read_text().strip() == "v1.0.1"


def test_file_without_version_line_raises(committed_repo):
    vf = committed_repo / "VERSION"
    vf.write_text("no version here\n")
    with pytest.raises(RepoError):
        version_command.run("patch", version_file=str(vf))


# --- model-decided (no part) ----------------------------------------------

def test_model_decides_bump_and_tags(committed_repo, capsys, monkeypatch):
    # Bare `karen version`: the model picks the part. Stub it to "minor"; from
    # v1.2.3 that must tag v1.3.0 and say the model chose it.
    _git(committed_repo, "tag", "-a", "v1.2.3", "-m", "Release v1.2.3")
    _new_commit(committed_repo)
    _stub_bump(monkeypatch, "minor")
    assert version_command.run() == 0
    assert "v1.3.0" in set(_git(committed_repo, "tag").stdout.split())
    out = capsys.readouterr().out
    assert "v1.3.0" in out
    assert "model" in out                       # reports it was model-chosen


def test_model_decides_first_release_from_no_tag(committed_repo, capsys, monkeypatch):
    # No prior tag: _decide_bump summarises the whole history and the model's
    # "major" starts the line at v1.0.0 (bumped from v0.0.0).
    _stub_bump(monkeypatch, "major")
    assert version_command.run() == 0
    assert "v1.0.0" in set(_git(committed_repo, "tag").stdout.split())


def test_tags_locally_and_prints_push_hint(committed_repo, capsys, monkeypatch):
    # karen only tags LOCALLY and tells the user to push with --tags; it never
    # pushes itself (a bare throwaway repo has no remote, so a push would error).
    _git(committed_repo, "tag", "-a", "v2.0.0", "-m", "Release v2.0.0")
    _new_commit(committed_repo)
    _stub_bump(monkeypatch, "patch")
    assert version_command.run() == 0
    assert "v2.0.1" in set(_git(committed_repo, "tag").stdout.split())
    out = capsys.readouterr().out
    assert "git push origin master --tags" in out


def test_model_unparseable_reply_raises(committed_repo, monkeypatch):
    # The model never returns a usable part; after the retries run() must give up
    # with a RepoError telling the user to pass a part explicitly -- not tag garbage.
    _git(committed_repo, "tag", "-a", "v1.0.0", "-m", "Release v1.0.0")
    _new_commit(committed_repo)
    _stub_bump(monkeypatch, "banana split, no idea")
    with pytest.raises(RepoError):
        version_command.run()
    assert _git(committed_repo, "tag").stdout.split() == ["v1.0.0"]        # nothing new


def test_model_not_called_when_part_forced(committed_repo, monkeypatch):
    # A forced part must NOT reach the model at all -- make suggest_bump explode so
    # the test fails loudly if run() ever consults it on the forced path.
    _git(committed_repo, "tag", "-a", "v1.0.0", "-m", "Release v1.0.0")

    def _boom(*a, **k):
        raise AssertionError("suggest_bump must not be called when a part is forced")

    monkeypatch.setattr(version_command.llm, "suggest_bump", _boom)
    version_command.run("patch")
    assert "v1.0.1" in set(_git(committed_repo, "tag").stdout.split())


def test_model_nothing_to_release_raises(git_repo, monkeypatch):
    # A repo with HEAD but no new commits since the last tag: changes_since returns
    # "" and _decide_bump must bail with "nothing to release" before calling the
    # model. Commit once, tag it, then ask to version with nothing new on top.
    subprocess.run(["git", "-C", str(git_repo), "commit", "--allow-empty", "-q",
                    "-m", "init"], check=True)
    _git(git_repo, "tag", "-a", "v1.0.0", "-m", "Release v1.0.0")
    monkeypatch.setenv("ANTHROPIC_API", "sk-ant-TEST")

    def _boom(*a, **k):
        raise AssertionError("must not call the model when there is nothing to release")

    monkeypatch.setattr(version_command.llm, "suggest_bump", _boom)
    with pytest.raises(RepoError):
        version_command.run()
