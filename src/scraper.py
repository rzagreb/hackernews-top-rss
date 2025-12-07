from __future__ import annotations

import datetime
import logging
import re
from typing import Literal, Optional

import httpx
from lxml import html

from src.models import FeedItem, StoryData
from src.rate_limiter import RateLimiter
from src.utils import arr_get, parse_human_date

log = logging.getLogger(__name__)

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
    Responsible for talking to the remote site (Hacker News today) and
    turning the result into a list of FeedItem instances.

    The only method that user code should rely on is fetch_feed_items.
    If you want to support a different site you can implement a class
    with the same interface and reuse the rest of the pipeline unchanged.
    """

    def __init__(self, client: Optional[httpx.Client] = None) -> None:
        self.url_base = "https://news.ycombinator.com"
        self.url_main = (
            f"{self.url_base}/front?day={datetime.datetime.now().isoformat()[:10]}"
        )
        self._client = client or httpx.Client(
            timeout=10.0,
            follow_redirects=True,
            headers=HEADERS,
        )

        self.rate_limiter = RateLimiter(min_interval_ms=2000.0, start=True)

    def fetch_feed_items(
        self,
        max_items: int = 30,
        min_points: int = 20,
        sort_by: Optional[Literal["points", "published"]] = "points",
    ) -> list[FeedItem]:
        """
        Fetch stories from the main page and return them as FeedItem objects.

        Args:
            max_items: Maximum number of items to return.
            min_points: Filter out stories that have fewer points than this.
        """
        log.info(f"Fetching feed items from {self.url_main}")
        tree = self._load_page_elements(self.url_main)
        stories = self._parse_main_page(tree)
        log.info(f"Found {len(stories)} stories on the main page")

        if sort_by == "points":
            stories.sort(key=lambda s: s.points or 0, reverse=True)
        elif sort_by == "published":
            stories.sort(key=lambda s: s.published or 0, reverse=True)

        rss_items: list[FeedItem] = []
        for idx, story in enumerate(stories):
            self.rate_limiter.wait_if_needed()
            log.info(f"[{idx + 1}/{len(stories)}] {story.title}")
            if len(rss_items) >= max_items:
                break

            if story.points is not None and story.points < min_points:
                log.info(
                    f"Skip story '{story.title}' because {story.points} < {min_points} required points"
                )
                continue

            self._try_fetch_story_comment(story)

            desc_parts = []
            if story.description:
                desc_parts.append(f"<p>{story.description}</p>")
            if story.top_comment:
                desc_parts.append(
                    f"<p><strong>Top Comment:</strong> <quote>{story.top_comment}</quote></p>"
                )
            desc_parts.append(
                f"<hr/>"
                f'<p><strong>Source:</strong> <a href="{story.url}">{story.url_domain()}</a></p>'
                f'<p><a href="{story.comments_url}">View All Comments</a></p>'
            )
            description = "".join(desc_parts)

            published: Optional[datetime.datetime] = None
            if story.age_text:
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

    def _load_page_elements(self, url: str) -> html.HtmlElement:
        log.info(f"Loading {url}")
        response = self._client.get(url)
        response.raise_for_status()
        return html.fromstring(response.text)

    def _parse_main_page(self, tree: html.HtmlElement) -> list[StoryData]:
        """
        Parse the Hacker News front page.

        The HTML structure is roughly:

        <tr class="athing" id="story-id">
            ... title row ...
        </tr>
        <tr>
            <td class="subtext">
                ... score, user, age, comments link ...
            </td>
        </tr>
        """
        if not isinstance(tree, html.HtmlElement):
            raise ValueError("tree must be an instance of lxml.html.HtmlElement")

        elems_parent = tree.xpath('..//tr[contains(@class,"athing")]/parent::table')
        if not elems_parent:
            return []
        elems_parent = elems_parent[0]

        # Structure: first <tr> is item, second <tr> is subtext, third <tr> is spacer
        items_data = []
        _item = None
        for elem_i, elem in enumerate(elems_parent.findall("tr")):
            # Skip spacer (appears after first two <tr> of each item)
            if elem.get("class") == "spacer":
                _item = None
                continue

            # Extract all from first <tr> and then move to next
            elems_title = elem.xpath('.//span[@class="titleline"]/a/text()')
            if elems_title:
                _item = StoryData(
                    title=elems_title[0],
                    url=elem.xpath('.//span[@class="titleline"]/a/@href')[0],
                    comments_url=f"{self.url_base}/item?id={elem.get('id')}",
                    order=elem_i,
                )
                continue

            # Extract all from second <tr> and then store item
            elems_subtext = elem.xpath('.//td[@class="subtext"]')
            if elems_subtext and _item:
                points_str = arr_get(elem.xpath('.//span[@class="score"]/text()'))
                if isinstance(points_str, str):
                    points_str = re.sub(r" points?$", "", points_str)
                    _item.points = int(points_str) if points_str else None

                _item.author = arr_get(elem.xpath('.//a[@class="hnuser"]/text()'))

                # extract time from
                _item.age_text = arr_get(elem.xpath('.//span[@class="age"]/text()'))
                if _item.age_text:
                    age_short = _item.age_text[:19]
                    _item.published = datetime.datetime.fromisoformat(age_short)

                items_data.append(_item)
                _item = None  # reset for next item
                continue
        return items_data

    def _try_fetch_story_comment(self, story: StoryData) -> Optional[str]:
        """
        Load the story comments page and extract the very first comment.

        Failures are deliberately swallowed so that a transient network
        issue on one story does not break the whole feed.
        """
        if not story.comments_url:
            return None

        print("Loading comments for story:", story.title)

        try:
            tree = self._load_page_elements(story.comments_url)
        except Exception as exc:
            log.warning(f"Could not load comments for '{story.title}': {exc}")
            return None

        print("Parsing comment page for story:", story.title)

        # Post description (sometimes empty)
        elems_toptext: list[html.HtmlElement] = tree.xpath('.//div[@class="toptext"]')
        elem_toptext = arr_get(elems_toptext)
        if elem_toptext is not None:
            inner_html: str = "".join(
                html.tostring(child, method="html", encoding="unicode")
                for child in elem_toptext.iterchildren()  # type: ignore
            )
            story.description = inner_html.strip()

        # Get very first comment
        elems_comments: list[html.HtmlElement] = tree.xpath(
            './/table[@class="comment-tree"]//tr/td[@class="default"]//div[contains(@class,"commtext")]'
        )
        elem_comment = arr_get(elems_comments)
        if elem_comment:
            story.top_comment = elem_comment.text_content().strip()
