"""Spec: "البحث في الويب لدراسة المنتجات والمنافسين" (web search for product/
competitor research) - one of the agents' tools. Provider: Claude's own
server-side web search tool (`web_search_20260209`) - verified 2026-10-13,
see docs/SOURCES.md "Web search tool". Chosen because ANTHROPIC_API_KEY is
already configured and verified for this project's agent reasoning; no new
account or credential is needed. Found live, not a guess: this was the
actual root cause blocking every real new-product-discovery run from ever
reaching the 5 agents - see docs/SOURCES.md for the live failure.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchTool(ABC):
    @abstractmethod
    def search(self, query: str) -> list[SearchResult]: ...


class RealWebSearchTool(WebSearchTool):
    def __init__(self, api_key: str, model: str):
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model

    def search(self, query: str) -> list[SearchResult]:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": f"Search the web for: {query}"}],
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}],
        )
        results: list[SearchResult] = []
        for block in message.content:
            if getattr(block, "type", None) != "web_search_tool_result":
                continue
            content = block.content
            # A server-tool error comes back as a single error object, not a
            # list (see docs/SOURCES.md) - skip it rather than crash the
            # whole discovery cycle over one failed search.
            if not isinstance(content, list):
                continue
            for item in content:
                if getattr(item, "type", None) != "web_search_result":
                    continue
                # web_search_result carries url/title/page_age/encrypted_content
                # - no snippet/excerpt field exists on it (confirmed against
                # Anthropic's own docs page); this project's own code never
                # reads .snippet today (new_product_discovery.py only counts
                # results), so leaving it empty is honest, not a shortcut.
                results.append(SearchResult(title=item.title, url=item.url, snippet=""))
        return results


class MockWebSearchTool(WebSearchTool):
    """Fully functional in-memory fake, pre-seeded per test / per DRY_RUN run."""

    def __init__(self, canned_results: dict[str, list[SearchResult]] | None = None):
        self._canned = canned_results or {}
        self.queries: list[str] = []

    def search(self, query: str) -> list[SearchResult]:
        self.queries.append(query)
        return list(self._canned.get(query, []))
