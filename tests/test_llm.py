"""Tests for llm.py -- request shape and auth, with urlopen faked (no network).

We never hit the real API: urllib.request.urlopen is monkeypatched to capture the
request and return a canned Messages-API body. This pins that the key is read from
the env and sent as x-api-key, and that the response text is extracted.
"""

from __future__ import annotations

import io
import json

import pytest

import llm
from checks import RepoError


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _canned(text):
    return _FakeResp(json.dumps({"content": [{"type": "text", "text": text}]}).encode())


def test_api_key_prefers_anthropic_api(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API", "primary")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fallback")
    assert llm.api_key() == "primary"


def test_api_key_falls_back(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fallback")
    assert llm.api_key() == "fallback"


def test_require_api_key_raises_when_unset(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RepoError):
        llm.require_api_key()


def test_api_url_default_and_override(monkeypatch):
    monkeypatch.delenv("KAREN_API_URL", raising=False)
    assert llm.api_url() == llm.API_URL
    monkeypatch.setenv("KAREN_API_URL", "http://127.0.0.1:9/v1/messages")
    assert llm.api_url() == "http://127.0.0.1:9/v1/messages"


def test_generate_sends_key_and_model_and_extracts_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API", "sk-ant-TEST")
    monkeypatch.delenv("KAREN_API_URL", raising=False)
    captured = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        captured["body"] = json.loads(req.data.decode())
        captured["timeout"] = timeout
        return _canned("Add greeting helper")

    monkeypatch.setattr(llm.urllib.request, "urlopen", _fake_urlopen)
    out = llm.generate_subject("the diff", model="claude-haiku-4-5-20251001")

    assert out == "Add greeting helper"
    assert captured["url"] == llm.API_URL
    assert captured["headers"]["x-api-key"] == "sk-ant-TEST"
    assert captured["headers"]["anthropic-version"] == llm.ANTHROPIC_VERSION
    assert captured["body"]["model"] == "claude-haiku-4-5-20251001"
    assert captured["body"]["max_tokens"] == 64
    assert captured["body"]["system"] == llm.SYSTEM_PROMPT
    assert "the diff" in captured["body"]["messages"][0]["content"]


def test_generate_returns_empty_on_network_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API", "sk-ant-TEST")

    def _boom(req, timeout=None):
        raise llm.urllib.error.URLError("no network")

    monkeypatch.setattr(llm.urllib.request, "urlopen", _boom)
    assert llm.generate_subject("d", model="m") == ""


def test_generate_returns_empty_on_contentless_response(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API", "sk-ant-TEST")

    def _err_body(req, timeout=None):
        return _FakeResp(json.dumps({"error": {"message": "bad key"}}).encode())

    monkeypatch.setattr(llm.urllib.request, "urlopen", _err_body)
    assert llm.generate_subject("d", model="m") == ""


def test_suggest_bump_sends_bump_prompt_and_extracts_text(monkeypatch):
    # The `karen version` path: same transport, but the BUMP system prompt/preamble
    # and a tiny token cap (one bare word).
    monkeypatch.setenv("ANTHROPIC_API", "sk-ant-TEST")
    monkeypatch.delenv("KAREN_API_URL", raising=False)
    captured = {}

    def _fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return _canned("minor")

    monkeypatch.setattr(llm.urllib.request, "urlopen", _fake_urlopen)
    out = llm.suggest_bump("the changes", model="claude-haiku-4-5-20251001")

    assert out == "minor"
    assert captured["body"]["system"] == llm.BUMP_SYSTEM_PROMPT
    assert captured["body"]["max_tokens"] == 16
    assert llm.BUMP_PREAMBLE in captured["body"]["messages"][0]["content"]
    assert "the changes" in captured["body"]["messages"][0]["content"]


def test_suggest_bump_returns_empty_on_network_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API", "sk-ant-TEST")

    def _boom(req, timeout=None):
        raise llm.urllib.error.URLError("no network")

    monkeypatch.setattr(llm.urllib.request, "urlopen", _boom)
    assert llm.suggest_bump("c", model="m") == ""
