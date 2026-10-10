"""Spec: "البحث في الويب لدراسة المنتجات والمنافسين" (web search for product/
competitor research) - one of the agents' tools. No search provider was
named in the spec, and none of the four APIs this project's verification
pass covered (Anthropic/Shopify/CJ/Telegram) is a web-search API, so
RealWebSearchTool is an honest stub - see docs/UNVERIFIED.md. Picking a
provider (Anthropic's own web_search tool-use feature, Bing/Google Custom
Search, SerpAPI, ...) is real, scoped, remaining work for whoever has
accounts with one of them.
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
    def __init__(self, **_kwargs):
        pass

    def search(self, query: str) -> list[SearchResult]:
        raise NotImplementedError(
            "No web search provider configured - see docs/UNVERIFIED.md "
            "(this project's spec named the capability but not a provider)."
        )


class MockWebSearchTool(WebSearchTool):
    """Fully functional in-memory fake, pre-seeded per test / per DRY_RUN run."""

    def __init__(self, canned_results: dict[str, list[SearchResult]] | None = None):
        self._canned = canned_results or {}
        self.queries: list[str] = []

    def search(self, query: str) -> list[SearchResult]:
        self.queries.append(query)
        return list(self._canned.get(query, []))
