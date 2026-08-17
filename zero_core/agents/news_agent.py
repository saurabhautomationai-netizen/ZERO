"""The Hindu Daily News Agent for ZERO.

Fetches and synthesizes real-time 5-10 line news digests across Business,
Share Market, Geopolitics, Politics, Sci-Tech, and Sports from The Hindu RSS feeds.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional
import urllib.request
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

THE_HINDU_FEEDS = {
    "Business & Markets": "https://www.thehindu.com/business/feeder/default.rss",
    "National Politics": "https://www.thehindu.com/news/national/feeder/default.rss",
    "Geopolitics": "https://www.thehindu.com/news/international/feeder/default.rss",
    "Science & Tech": "https://www.thehindu.com/sci-tech/feeder/default.rss",
    "Sports": "https://www.thehindu.com/sport/feeder/default.rss",
}


class NewsAgent:
    """Fetches and summarizes categorized headlines from The Hindu."""

    def __init__(self, feeds: Optional[Dict[str, str]] = None, timeout: int = 8):
        self.feeds = feeds or THE_HINDU_FEEDS
        self.timeout = timeout

    def fetch_category_headlines(self, url: str, limit: int = 2) -> List[str]:
        """Fetches top headline titles from an RSS endpoint."""
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ZERO-AI/1.0"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                root = ET.fromstring(resp.read())
                items = root.findall("./channel/item")
                headlines = []
                for item in items[:limit]:
                    title_elem = item.find("title")
                    if title_elem is not None and title_elem.text:
                        headlines.append(title_elem.text.strip())
                return headlines
        except Exception as e:
            logger.warning("Failed to fetch RSS from %s: %s", url, e)
            return []

    def get_daily_digest(self) -> str:
        """Generates a concise 5-10 line executive summary across all categories."""
        lines = [
            "📰 *The Hindu — Daily Executive News Digest*",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        icons = {
            "Business & Markets": "📈",
            "National Politics": "🏛️",
            "Geopolitics": "🌍",
            "Science & Tech": "🔬",
            "Sports": "🏆",
        }

        has_any = False
        for category, url in self.feeds.items():
            icon = icons.get(category, "•")
            headlines = self.fetch_category_headlines(url, limit=2)
            if headlines:
                has_any = True
                lines.append(f"\n{icon} *{category}*:")
                for h in headlines:
                    lines.append(f"  • {h}")

        if not has_any:
            return "📰 *The Hindu News*: Unable to fetch latest feeds. Please check network connection."

        lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚡ _Source: The Hindu Live Feeds • Curated by ZERO_")
        return "\n".join(lines)


# Singleton instance
DEFAULT_NEWS_AGENT = NewsAgent()
