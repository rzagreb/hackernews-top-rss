from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from src.models import FeedItem, FeedMetadata
from src.utils import ensure_utc, format_rfc2822


def generate_rss2(meta: FeedMetadata, items: list[FeedItem]) -> str:
    """Build an RSS 2.0 feed as a UTF-8 XML string."""
    rss_el = ET.Element("rss", version="2.0")
    channel_el = ET.SubElement(rss_el, "channel")

    # core fields
    ET.SubElement(channel_el, "title").text = meta.title
    ET.SubElement(channel_el, "link").text = meta.link
    ET.SubElement(channel_el, "description").text = meta.description
    ET.SubElement(channel_el, "language").text = meta.language

    # Recommended but optional fields
    now = ensure_utc(datetime.now(timezone.utc))
    last_build = format_rfc2822(now)
    ET.SubElement(channel_el, "lastBuildDate").text = last_build

    for item in items:
        item_el = ET.SubElement(channel_el, "item")
        ET.SubElement(item_el, "title").text = item.title
        ET.SubElement(item_el, "link").text = item.link

        guid_text = item.link or item.guid
        if guid_text:
            guid_el = ET.SubElement(item_el, "guid")
            guid_el.text = guid_text
            # Links are usually stable enough but not guaranteed to be permanent
            guid_el.set("isPermaLink", str(item.is_permalink).lower())

        if item.published is not None:
            ET.SubElement(item_el, "pubDate").text = format_rfc2822(item.published)

        if item.description:
            ET.SubElement(item_el, "description").text = item.description

        if item.categories:
            for category in item.categories:
                if category:
                    ET.SubElement(item_el, "category").text = category

        if item.extra:
            for key, value in item.extra.items():
                if key and value:
                    ET.SubElement(item_el, key).text = str(value)

    xml_bytes = ET.tostring(rss_el, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")
