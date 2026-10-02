"""version.py - semver parsing and bumping for `karen version`.

`karen version <part>` reads the latest `vX.Y.Z` git tag, bumps the requested
part, and the caller creates the annotated tag. Pure logic here (no git, no IO)
so it is trivially unit-tested; git_io does the tagging.

Tags are `v`-prefixed semver cores (vMAJOR.MINOR.PATCH). Pre-release/build
metadata (`-rc1`, `+build`) is intentionally NOT supported yet -- the tool bumps
clean release cores; that is the 90% case and keeps the ordering unambiguous.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from checks import die

_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

PARTS = ("major", "minor", "patch")


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def tag(self) -> str:
        return f"v{self}"

    def bump(self, part: str) -> "Version":
        """Return a new Version with `part` incremented and lower parts reset to 0."""
        if part == "major":
            return Version(self.major + 1, 0, 0)
        if part == "minor":
            return Version(self.major, self.minor + 1, 0)
        if part == "patch":
            return Version(self.major, self.minor, self.patch + 1)
        die(f"unknown version part: {part} (use one of: {', '.join(PARTS)})")


def parse(text: str) -> "Version | None":
    """Parse a `vX.Y.Z` (or `X.Y.Z`) string to a Version, or None if it is not one."""
    m = _SEMVER_RE.match(text.strip())
    if not m:
        return None
    return Version(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def latest(tags: list[str]) -> "Version | None":
    """The highest semver Version among `tags`, or None when there are no semver tags.

    Sorts by the PARSED version (tag commit-date is not version order), so the
    newest release is unambiguous even if tags were created out of order.
    """
    versions = [v for v in (parse(t) for t in tags) if v is not None]
    return max(versions) if versions else None


def next_version(tags: list[str], part: str) -> "Version":
    """The version `karen version <part>` would create: latest tag bumped, or the
    first release (v0.0.1 / v0.1.0 / v1.0.0) bumped from v0.0.0 when there are none."""
    current = latest(tags) or Version(0, 0, 0)
    return current.bump(part)
