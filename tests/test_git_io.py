"""Tests for git_io.py -- the git plumbing wrappers, against throwaway repos.

These run REAL git, but only inside the `git_repo`/`staged_repo` fixtures (fresh
repos under tmp_path). Nothing in any real repository is read or modified.
"""

from __future__ import annotations

import subprocess

import pytest

import git_io
from checks import RepoError


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)


def test_no_staged_changes_on_fresh_repo(git_repo):
    assert git_io.has_staged_changes() is False


def test_staged_changes_detected(staged_repo):
    assert git_io.has_staged_changes() is True


def test_staged_diff_contains_stat_and_body(staged_repo):
    diff = git_io.staged_diff()
    assert "app.py" in diff          # the --stat names the file
    assert "---" in diff             # the separator between stat and body
    assert "def hi" in diff          # the body carries the actual change


def test_commit_records_message(staged_repo):
    git_io.commit("Add greeting helper")
    log = _git(staged_repo, "log", "--oneline", "-1").stdout
    assert "Add greeting helper" in log
    # After committing, nothing is staged.
    assert git_io.has_staged_changes() is False


def test_head_has_commits_tracks_state(staged_repo):
    assert git_io.head_has_commits() is False
    git_io.commit("first")
    assert git_io.head_has_commits() is True


def test_list_version_tags_filters_to_v_prefix(staged_repo):
    git_io.commit("first")
    _git(staged_repo, "tag", "v1.0.0")
    _git(staged_repo, "tag", "v1.2.0")
    _git(staged_repo, "tag", "nightly")          # not a v-tag
    tags = set(git_io.list_version_tags())
    assert tags == {"v1.0.0", "v1.2.0"}


def test_create_annotated_tag_and_exists(staged_repo):
    git_io.commit("first")
    assert git_io.tag_exists("v1.0.0") is False
    git_io.create_annotated_tag("v1.0.0", "Release v1.0.0")
    assert git_io.tag_exists("v1.0.0") is True
    # It is annotated (has a tag object), not lightweight.
    kind = _git(staged_repo, "cat-file", "-t", "v1.0.0").stdout.strip()
    assert kind == "tag"


def test_create_duplicate_tag_dies(staged_repo):
    git_io.commit("first")
    git_io.create_annotated_tag("v1.0.0", "Release v1.0.0")
    with pytest.raises(RepoError):
        git_io.create_annotated_tag("v1.0.0", "Release v1.0.0")


def test_changes_since_tag_carries_log_and_diff(staged_repo):
    # Tag a baseline, then add a new commit on top; changes_since(tag) must surface
    # the new commit's subject and its diff -- this is what the bump model reads.
    git_io.commit("baseline")
    _git(staged_repo, "tag", "v1.0.0")
    (staged_repo / "feature.py").write_text("x = 1\n")
    _git(staged_repo, "add", "feature.py")
    git_io.commit("Add feature")

    changes = git_io.changes_since("v1.0.0")
    assert "Add feature" in changes          # the new commit subject (log)
    assert "feature.py" in changes           # the --stat / diff body
    assert "baseline" not in changes         # nothing from before the tag


def test_changes_since_empty_when_nothing_new(staged_repo):
    git_io.commit("baseline")
    _git(staged_repo, "tag", "v1.0.0")
    assert git_io.changes_since("v1.0.0") == ""     # no commits after the tag


def test_changes_since_empty_ref_covers_whole_history(staged_repo):
    # No previous tag -> ref="" -> summarise everything since the start of history.
    git_io.commit("first")
    changes = git_io.changes_since("")
    assert "first" in changes
