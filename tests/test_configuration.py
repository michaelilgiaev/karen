"""Tests for configuration.model() -- the only thing left: the built-in default
with a $KAREN_MODEL override. There is no saved config any more."""

from __future__ import annotations

import configuration


def test_default_model_when_env_unset(monkeypatch):
    monkeypatch.delenv("KAREN_MODEL", raising=False)
    assert configuration.model() == configuration.DEFAULT_MODEL


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv("KAREN_MODEL", "claude-sonnet-4-6")
    assert configuration.model() == "claude-sonnet-4-6"


def test_blank_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("KAREN_MODEL", "   ")
    assert configuration.model() == configuration.DEFAULT_MODEL
