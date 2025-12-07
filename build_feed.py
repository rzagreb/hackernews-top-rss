from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.models import FeedMetadata
from src.rss import generate_rss2
from src.scraper import RssItemsMaker

logging.basicConfig(level=logging.INFO)

DEFAULT_MIN_POINTS = 100
DEFAULT_MAX_ITEMS = 15


def build_feed(max_items: int, min_points: int) -> str:
    """
    High level function that ties metadata, scraper, and RSS generator together.

    This function is intentionally generic so it can be reused for other feeds
    by swapping out the metadata or items maker.
    """

    rss_meta = FeedMetadata(
        title="Hacker News Top Stories",
        link="https://news.ycombinator.com/",
        description="Top stories from Hacker News",
    )

    items_maker = RssItemsMaker()
    rss_items = items_maker.fetch_feed_items(max_items=max_items, min_points=min_points)

    xml_data = generate_rss2(rss_meta, rss_items)
    return xml_data


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the Hacker News RSS feed.")
    parser.add_argument(
        "--output",
        type=str,
        default="feeds/hacker-news.xml",
        help="Output path for the generated RSS XML)",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=DEFAULT_MAX_ITEMS,
        help="Maximum number of items to include in the feed.",
    )
    parser.add_argument(
        "--min-points",
        type=int,
        default=DEFAULT_MIN_POINTS,
        help="Minimum number of points required for a story to be included.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> str:
    args = parse_args(argv)
    feed_xml = build_feed(max_items=args.max_items, min_points=args.min_points)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(feed_xml, encoding="utf-8")
    return feed_xml


if __name__ == "__main__":
    # poetry run python build_feed.py --output feeds/hacker-news.xml
    main()
