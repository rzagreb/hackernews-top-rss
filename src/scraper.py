from __future__ import annotations

import datetime
import logging
import re
from typing import Literal, Optional

import httpx

from src.models import FeedItem, StoryData
from src.rate_limiter import RateLimiter
from src.utils import arr_get, parse_human_date

log = logging.getLogger(__name__)


HEADERS = {
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "DNT": "1",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:144.0) Gecko/20100101 Firefox/144.0",
}


class RssItemsMaker:
    """
    Responsible for talking to the remote site (Hacker News) and
    turning the result into a list of FeedItem instances.

    The only method that user code should rely on is fetch_feed_items.
    If you want to support a different site you can implement a class
    with the same interface and reuse the rest of the pipeline unchanged.
    """

    def __init__(self, client: Optional[httpx.Client] = None) -> None:
        self.url_base = "https://news.ycombinator.com"
        self.api_base = "https://hacker-news.firebaseio.com/v0"
        self._client = client or httpx.Client(
            timeout=10.0,
            follow_redirects=True,
            headers=HEADERS,
        )

        # 1 second between requests by default - polite for the public API
        self.rate_limiter = RateLimiter(min_interval_ms=1000.0, start=True)

    def fetch_feed_items(
        self,
        max_items: int = 30,
        min_points: int = 20,
        sort_by: Optional[Literal["points", "published"]] = "points",
    ) -> list[FeedItem]:
        """
        Fetch stories from the Hacker News official Firebase API and return
        them as FeedItem objects.

        Args:
            max_items: Maximum number of items to return.
            min_points: Filter out stories that have fewer points than this.
            sort_by: How to sort the resulting feed.
        """
        log.info("Fetching feed items from Hacker News Firebase API")

        story_ids = self._fetch_top_story_ids()
        if not story_ids:
            return []

        # We do not need all 500 ids - take a small oversampling so that
        # filtering by points still leaves enough items.
        oversample = max(max_items * 3, max_items)
        story_ids = story_ids[:oversample]

        stories_with_data: list[tuple[StoryData, dict]] = []

        for order, story_id in enumerate(story_ids):
            result = self._fetch_story_from_api(story_id, order=order)
            if result is None:
                continue
            story, story_data = result

            stories_with_data.append((story, story_data))

        if not stories_with_data:
            return []

        # Sort in memory according to the requested key.
        if sort_by == "points":
            stories_with_data.sort(key=lambda sd: sd[0].points or 0, reverse=True)
        elif sort_by == "published":
            stories_with_data.sort(
                key=lambda sd: sd[0].published or datetime.datetime.fromtimestamp(0),
                reverse=True,
            )

        rss_items: list[FeedItem] = []

        for idx, (story, story_data) in enumerate(stories_with_data):
            # Respect the max_items and min_points arguments.
            if len(rss_items) >= max_items:
                break

            if story.points is not None and story.points < min_points:
                log.info(
                    "Skip story '%s' because %s < %s required points",
                    story.title,
                    story.points,
                    min_points,
                )
                continue

            self.rate_limiter.wait_if_needed()
            log.info("[%s/%s] %s", idx + 1, len(stories_with_data), story.title)

            # Enrich with description and top comment from the API.
            self._try_fetch_story_comment(story, story_data=story_data)

            desc_parts: list[str] = []
            desc_parts.append(
                f'<p><strong>Source:</strong> <a href="{story.url}">{story.url_domain()}</a></p>'
            )
            if story.description:
                desc_parts.append(f"<p>{story.description}</p>")
            if story.top_comment:
                desc_parts.append(
                    f"""
                    <hr/>
                    <div><b>Top Comment:</b></div>
                    <blockquote style="margin:1.5em 0; padding:1em 1.5em; border-left:4px solid #ccc; background-color:#f9f9f9; font-style:italic;">
                    <p>{story.top_comment}</p>
                    </blockquote>
                    """
                )
            desc_parts.append(
                f"<p><strong>Points:</strong> {story.points or 0} | <strong>Author:</strong> {story.author or 'unknown'}</p>"
                f'<p><a href="{story.comments_url}">View All Comments</a></p>'
            )

            description = "".join(desc_parts)

            # Prefer the explicit published datetime populated from the API.
            published: Optional[datetime.datetime] = story.published
            if not published and getattr(story, "age_text", None):
                if story.age_text is not None:
                    # Backwards compatible fallback for any older StoryData values
                    published = parse_human_date(story.age_text) or None

            rss_items.append(
                FeedItem(
                    title=story.title,
                    link=story.comments_url,
                    description=description,
                    published=published,
                    guid=story.url,
                    categories=None,
                    extra={
                        "hn_points": story.points,
                        "hn_author": story.author,
                        "hn_order": story.order,
                    },
                )
            )

        return rss_items

    # API helpers
    # ------------------------------------------------------------

    def _fetch_top_story_ids(self) -> list[int]:
        """
        Return a list of story ids corresponding to the current HN front page.

        This uses the official Firebase API:
            GET /v0/topstories.json
        """
        url = f"{self.api_base}/topstories.json"
        log.info("Loading top stories ids from %s", url)
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except Exception as exc:
            log.warning("Could not load top stories: %s", exc)
            return []

        data = response.json()
        if not isinstance(data, list):
            log.warning("Unexpected response for topstories: %r", data)
            return []

        ids: list[int] = []
        for raw in data:
            try:
                ids.append(int(raw))
            except (TypeError, ValueError):
                continue
        return ids

    def _fetch_story_from_api(
        self,
        story_id: int,
        order: int,
    ) -> Optional[tuple[StoryData, dict]]:
        """
        Load a story from the Firebase API and build a StoryData instance.

        GET /v0/item/<id>.json
        """
        url = f"{self.api_base}/item/{story_id}.json"
        log.debug("Loading story %s from %s", story_id, url)
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except Exception as exc:
            log.warning("Could not load story %s: %s", story_id, exc)
            return None

        data = response.json() or {}
        if data.get("type") != "story":
            # Skip jobs, polls, comments, etc.
            return None

        title = data.get("title") or f"HN story {story_id}"
        url_out = data.get("url") or f"{self.url_base}/item?id={story_id}"

        story = StoryData(
            title=title,
            url=url_out,
            comments_url=f"{self.url_base}/item?id={story_id}",
            order=order,
        )

        story.points = data.get("score")
        story.author = data.get("by")
        timestamp = data.get("time")
        if isinstance(timestamp, (int, float)):
            story.published = datetime.datetime.fromtimestamp(timestamp)
        else:
            story.published = None

        # For text submissions like Ask HN, HN stores the body in `text`.
        text_html = data.get("text")
        if isinstance(text_html, str):
            story.description = text_html

        return story, data

    def _get_item_json(self, item_id: int) -> Optional[dict]:
        """
        Convenience wrapper to load any item (story or comment) from the API.
        """
        url = f"{self.api_base}/item/{item_id}.json"
        log.debug("Loading item %s from %s", item_id, url)
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except Exception as exc:
            log.warning("Could not load item %s: %s", item_id, exc)
            return None
        return response.json() or {}

    @staticmethod
    def _extract_item_id_from_url(url: Optional[str]) -> Optional[int]:
        if not url:
            return None
        match = re.search(r"id=(\d+)", url)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _try_fetch_story_comment(
        self,
        story: StoryData,
        story_data: Optional[dict] = None,
    ) -> Optional[str]:
        """
        Load the story comments through the Firebase API and extract the
        first comment text, as well as ensuring the story body is filled.

        Failures are deliberately swallowed so that a transient network
        issue on one story does not break the whole feed.
        """
        # Ensure we have the story JSON available.
        if story_data is None:
            story_id = self._extract_item_id_from_url(
                getattr(story, "comments_url", None)
            )
            if story_id is None:
                return None
            story_data = self._get_item_json(story_id)
            if not story_data:
                return None

        # Populate description from the story body if available.
        text_html = story_data.get("text")
        if isinstance(text_html, str) and not getattr(story, "description", None):
            story.description = text_html

        # Identify the first top-level comment from the kids list.
        kids = story_data.get("kids") or []
        first_comment_id = arr_get(kids)
        if not first_comment_id:
            return None

        comment_data = self._get_item_json(int(first_comment_id))
        if not comment_data:
            return None

        comment_text = comment_data.get("text")
        if isinstance(comment_text, str):
            story.top_comment = comment_text

        return story.top_comment
