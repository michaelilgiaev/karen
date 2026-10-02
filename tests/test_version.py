"""Tests for version.py -- semver parse / bump / latest / next, all pure logic."""

from __future__ import annotations

import pytest

import version
from checks import RepoError


@pytest.mark.parametrize(
    "text,expected",
    [
        ("v1.2.3", version.Version(1, 2, 3)),
        ("1.2.3", version.Version(1, 2, 3)),
        ("  v0.0.1  ", version.Version(0, 0, 1)),
        ("v10.20.30", version.Version(10, 20, 30)),
    ],
)
def test_parse_valid(text, expected):
    assert version.parse(text) == expected


@pytest.mark.parametrize("text", ["", "v1.2", "1.2.3.4", "v1.2.x", "release-1", "vA.B.C"])
def test_parse_invalid_returns_none(text):
    assert version.parse(text) is None


def test_bump_major_resets_lower():
    assert version.Version(1, 4, 9).bump("major") == version.Version(2, 0, 0)


def test_bump_minor_resets_patch():
    assert version.Version(1, 4, 9).bump("minor") == version.Version(1, 5, 0)


def test_bump_patch():
    assert version.Version(1, 4, 9).bump("patch") == version.Version(1, 4, 10)


def test_bump_unknown_part_raises():
    with pytest.raises(RepoError):
        version.Version(1, 0, 0).bump("banana")


def test_tag_property():
    assert version.Version(2, 1, 0).tag == "v2.1.0"


def test_latest_picks_highest_by_version_not_tag_order():
    # Tag order is irrelevant; the highest PARSED version wins.
    tags = ["v1.0.0", "v2.3.1", "v2.3.0", "v0.9.9", "not-a-tag"]
    assert version.latest(tags) == version.Version(2, 3, 1)


def test_latest_none_when_no_semver_tags():
    assert version.latest(["nightly", "release", "foo"]) is None
    assert version.latest([]) is None


def test_next_version_from_existing():
    assert version.next_version(["v1.2.3"], "minor") == version.Version(1, 3, 0)


def test_next_version_from_empty_starts_at_zero():
    # No tags -> start from v0.0.0, so the first patch release is v0.0.1.
    assert version.next_version([], "patch") == version.Version(0, 0, 1)
    assert version.next_version([], "minor") == version.Version(0, 1, 0)
    assert version.next_version([], "major") == version.Version(1, 0, 0)
