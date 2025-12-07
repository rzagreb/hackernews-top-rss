from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class FeedMetadata:
    title: str
    link: str
    description: str
    language: str = "en-us"


@dataclass
class FeedItem:
    title: str
    link: str
    description: str = ""
    published: Optional[datetime] = None
    guid: Optional[str] = None
    categories: Optional[List[str]] = None
    is_permalink: bool = True
    extra: Optional[dict] = None


@dataclass
class Feed:
    metadata: FeedMetadata
    items: list[FeedItem]


@dataclass
class StoryData:
    """
    Lightweight structure representing a single story row on Hacker News.

    This keeps the parsing layer separate from the FeedItem mapping layer
    which makes it easier to adapt the scraper for other websites later.
    """

    title: str
    url: str
    comments_url: str
    order: int

    points: Optional[int] = None
    author: Optional[str] = None
    age_text: Optional[str] = None
    published: Optional[datetime] = None

    description: Optional[str] = None
    top_comment: Optional[str] = None

    def url_domain(self) -> str:
        """Extract the domain from the story URL for display purposes."""
        from urllib.parse import urlparse

        parsed = urlparse(self.url)
        return parsed.netloc or "news.ycombinator.com"
