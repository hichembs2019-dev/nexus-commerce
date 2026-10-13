"""Unit tests for RealWebSearchTool - verified 2026-10-13, see docs/SOURCES.md
"Web search tool". The real anthropic.Anthropic().messages.create() call is
faked here (it needs a real API call); everything above that is real project
code, including the block-type parsing.
"""
from __future__ import annotations

import pytest

from src.tools.web_search import RealWebSearchTool, SearchResult


class _FakeBlock:
    def __init__(self, type_: str, **kwargs):
        self.type = type_
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeMessage:
    def __init__(self, content: list):
        self.content = content


def _tool(monkeypatch, response_content: list) -> tuple[RealWebSearchTool, list]:
    calls = []

    class _FakeMessages:
        def create(self, *, model, max_tokens, messages, tools):
            calls.append({"model": model, "max_tokens": max_tokens, "messages": messages, "tools": tools})
            return _FakeMessage(response_content)

    class _FakeClient:
        def __init__(self, *, api_key):
            self.messages = _FakeMessages()

    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)

    tool = RealWebSearchTool(api_key="fake-key", model="claude-sonnet-5-5")
    return tool, calls


def test_search_sends_the_query_and_declares_the_web_search_tool(monkeypatch):
    tool, calls = _tool(monkeypatch, [])

    tool.search("wireless earbuds price")

    assert len(calls) == 1
    call = calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["messages"] == [{"role": "user", "content": "Search the web for: wireless earbuds price"}]
    assert call["tools"] == [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}]


def test_search_maps_real_web_search_result_blocks_without_a_snippet(monkeypatch):
    response_content = [
        _FakeBlock("text", text="I'll search for that."),
        _FakeBlock("server_tool_use", id="srvtoolu_1", name="web_search", input={"query": "x"}),
        _FakeBlock(
            "web_search_tool_result",
            tool_use_id="srvtoolu_1",
            content=[
                _FakeBlock(
                    "web_search_result",
                    url="https://example.com/product",
                    title="Example Product - Example Store",
                    page_age="April 30, 2025",
                    encrypted_content="abc123",
                ),
            ],
        ),
        _FakeBlock("text", text="Based on the search results, prices range..."),
    ]
    tool, _ = _tool(monkeypatch, response_content)

    results = tool.search("example product price")

    assert results == [
        SearchResult(title="Example Product - Example Store", url="https://example.com/product", snippet="")
    ]


def test_search_returns_empty_list_when_the_tool_result_has_no_matching_blocks(monkeypatch):
    tool, _ = _tool(monkeypatch, [_FakeBlock("text", text="No search needed.")])

    assert tool.search("something") == []


def test_search_skips_a_server_tool_error_result_instead_of_crashing(monkeypatch):
    # A server-tool error comes back as a single error object (not a list)
    # per docs/SOURCES.md - e.g. {"type": "web_search_tool_result_error",
    # "error_code": "max_uses_exceeded"}. isinstance(content, list) is False
    # for it, so it's skipped rather than raising.
    response_content = [
        _FakeBlock(
            "web_search_tool_result",
            tool_use_id="srvtoolu_1",
            content=_FakeBlock("web_search_tool_result_error", error_code="max_uses_exceeded"),
        ),
    ]
    tool, _ = _tool(monkeypatch, response_content)

    assert tool.search("something") == []
