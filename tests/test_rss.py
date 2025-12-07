import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import context  # noqa: F401

from src.models import FeedItem, FeedMetadata
from src.rss import generate_rss2
from src.utils import ensure_utc, format_rfc2822


class TestRSS(unittest.TestCase):
    def test_format_rfc2822_utc_and_naive(self):
        naive = datetime(2024, 1, 1, 12, 0, 0)
        aware = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        s1 = format_rfc2822(naive)
        s2 = format_rfc2822(aware)

        assert "2024" in s1
        assert "2024" in s2
        assert "GMT" in s1 or "+0000" in s1
        assert s1 == s2

    def test_generate_rss2_basic_structure(self):
        meta = FeedMetadata(
            title="Test Feed",
            link="https://example.com",
            description="Example description",
        )

        items = [
            FeedItem(
                title="Item 1",
                link="https://example.com/1",
                description="First item",
                published=ensure_utc(datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)),
                guid="item-1",
                categories=["category-a", "category-b"],
            ),
            FeedItem(
                title="Item 2",
                link="https://example.com/2",
            ),
        ]

        xml = generate_rss2(meta, items)
        root = ET.fromstring(xml)

        assert root.tag == "rss"
        assert root.attrib.get("version") == "2.0"

        channel = root.find("channel")
        assert channel is not None
        assert channel.findtext("title") == meta.title
        assert channel.findtext("link") == meta.link
        assert channel.findtext("description") == meta.description

        item_elements = channel.findall("item")
        assert len(item_elements) == 2

        first_item = item_elements[0]
        assert first_item.findtext("title") == "Item 1"
        assert first_item.findtext("link") == "https://example.com/1"
        assert first_item.findtext("guid") == "https://example.com/1"
        assert first_item.find("pubDate") is not None

        categories = [c.text for c in first_item.findall("category")]
        assert categories == ["category-a", "category-b"]
