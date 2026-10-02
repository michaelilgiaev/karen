"""Tests for command_line_interface.main -- dispatch, usage, and arg parsing.

Subcommand bodies are stubbed where they would do IO; this file only checks that
`main` routes argv correctly and reports errors with the right exit codes.
"""

from __future__ import annotations

import pytest

import command_line_interface as cli


def test_help_prints_usage_and_exits_zero(capsys):
    assert cli.main(["help"]) == 0
    out = capsys.readouterr().out
    assert "karen" in out
    assert "karen commit" in out
    assert "karen version" in out


def test_no_args_defaults_to_help(capsys):
    assert cli.main([]) == 0
    assert "USAGE" in capsys.readouterr().out


def test_unknown_subcommand_is_error(capsys):
    assert cli.main(["frobnicate"]) == 2
    assert "unknown subcommand" in capsys.readouterr().err


def test_commit_dispatches(monkeypatch):
    monkeypatch.setattr(cli.commit_command, "run", lambda: 0)
    assert cli.main(["commit"]) == 0


def test_version_no_part_dispatches_empty(monkeypatch):
    # No part is valid now: the CLI passes part="" through and version_command
    # asks the model to decide.
    seen = {}
    monkeypatch.setattr(cli.version_command, "run",
                        lambda part="", *, version_file="":
                        seen.update(part=part) or 0)
    assert cli.main(["version"]) == 0
    assert seen["part"] == ""


def test_version_dispatches_part_and_flags(monkeypatch):
    seen = {}

    def _fake(part, *, version_file=""):
        seen.update(part=part, version_file=version_file)
        return 0

    monkeypatch.setattr(cli.version_command, "run", _fake)
    assert cli.main(["version", "minor", "--file", "VERSION"]) == 0
    assert seen == {"part": "minor", "version_file": "VERSION"}


def test_version_file_equals_form(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli.version_command, "run",
                        lambda part, *, version_file="": seen.update(
                            vf=version_file) or 0)
    cli.main(["version", "patch", "--file=pkg/VERSION"])
    assert seen["vf"] == "pkg/VERSION"


def test_version_unknown_flag_is_error(capsys):
    assert cli.main(["version", "patch", "--nope"]) == 2
    assert "unknown flag" in capsys.readouterr().err


def test_config_subcommand_is_gone(capsys):
    # `karen config` was removed; it must now be an unknown subcommand, not a crash.
    assert cli.main(["config"]) == 2
    assert "unknown subcommand" in capsys.readouterr().err


def test_repoerror_becomes_exit_1(monkeypatch, capsys):
    from checks import RepoError

    def _raise():
        raise RepoError("not inside a git repository.")

    monkeypatch.setattr(cli.commit_command, "run", _raise)
    assert cli.main(["commit"]) == 1
    assert "not inside a git repository" in capsys.readouterr().err
