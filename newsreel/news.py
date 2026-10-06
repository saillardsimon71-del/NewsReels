from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape

from .models import NewsItem


class NewsProviderError(RuntimeError):
    pass


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_rss_text(value: str) -> str:
    text = unescape(value or "")
    text = _HTML_TAG_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


class GoogleNewsRSS:
    """Small dependency-free French Google News RSS client."""

    def __init__(self, timeout: int = 25):
        self.timeout = timeout

    def fetch(self, query: str, limit: int = 12) -> list[NewsItem]:
        if not query.strip():
            raise ValueError("Indiquez un thème ou une requête d'actualité.")
        params = urllib.parse.urlencode(
            {"q": query.strip(), "hl": "fr", "gl": "FR", "ceid": "FR:fr"}
        )
        url = f"https://news.google.com/rss/search?{params}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "NewsReel/2.0 (+local news bulletin generator)"},
        )
        xml: bytes | None = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    xml = response.read()
                break
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                if attempt == 2:
                    break
                time.sleep(0.5 * (2**attempt))
        if xml is None:
            raise NewsProviderError(
                f"Impossible de récupérer Google News RSS après 3 tentatives: {last_error}"
            )
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise NewsProviderError("Google News a renvoyé un flux RSS illisible.") from exc
        items: list[NewsItem] = []
        seen_titles: set[str] = set()
        for item in root.findall("./channel/item"):
            source_node = item.find("source")
            summary_node = item.find("description")
            news = NewsItem(
                title=_clean_rss_text(item.findtext("title") or ""),
                url=(item.findtext("link") or "").strip(),
                source=_clean_rss_text(source_node.text or "") if source_node is not None else "",
                published=(item.findtext("pubDate") or "").strip(),
                summary=_clean_rss_text(summary_node.text or "")
                if summary_node is not None
                else "",
            )
            title_key = news.title.casefold()
            if news.title and news.url and title_key not in seen_titles:
                seen_titles.add(title_key)
                items.append(news)
            if len(items) >= limit:
                break
        if not items:
            raise NewsProviderError(
                "Google News n'a renvoyé aucun article exploitable pour cette recherche."
            )
        return items
