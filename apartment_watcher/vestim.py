"""Scraper for VestiM Verhuurmakelaars (https://www.vestim.nl)."""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .listing import Listing, first_int
from .session import PAGE_DELAY, TIMEOUT, new_session

SOURCE = "Vestim"
BASE_URL = "https://www.vestim.nl"
# The Amsterdam office includes nearby towns; the watcher filters by city afterwards.
SEARCH_URL = f"{BASE_URL}/woningen?status=for_rent&kantoor=amsterdam"
MAX_PAGES = 20
_TOTAL_RE = re.compile(r"(\d+)\s+woning(?:en)?\b")  # e.g. "10 woningen"


def parse_page(html: str) -> tuple[list[Listing], str | None]:
    """Return the listings on a /woningen page and the URL of the next page, if any."""
    soup = BeautifulSoup(html, "html.parser")
    listings = []
    for card in soup.select("div.vm-listing-block a.vm-listing-block2[href]"):
        url = urljoin(BASE_URL, card["href"])
        # Titles look like "Amsterdam, Jacob van Lennepkade".
        title = _text(card.select_one(".vm-listing-title"))
        city = title.partition(",")[0].strip() if "," in title else ""
        # The label is either an availability date ("Per 12 Oktober 2026") or a tagline ("Ruim appartement").
        label = _text(card.select_one(".vm-listing-label"))
        listings.append(
            Listing(
                source=SOURCE,
                listing_id=url.rstrip("/").rsplit("/", 1)[-1],
                url=url,
                title=title,
                city=city,
                status=_text(card.select_one(".vm-listing-status")),
                price=_text(card.select_one(".vm-listing-price")) or None,
                size_m2=first_int(_text(card.select_one('li[title^="Oppervlakte"]'))),
                bedrooms=first_int(_text(card.select_one('li[title^="Slaapkamer"]'))),
                available=label if label.startswith("Per ") else None,
            )
        )
    next_link = soup.select_one('a.page-link[aria-label="Next"][href]')
    next_url = urljoin(BASE_URL, next_link["href"]) if next_link else None
    return listings, next_url


def parse_total(html: str) -> int:
    """Number of results the page says it has; raises if the counter is gone."""
    match = _TOTAL_RE.search(_text(BeautifulSoup(html, "html.parser").select_one(".listing-tools-wrap")))
    if match is None:
        raise RuntimeError("Vestim: result count not found; the page layout may have changed")
    return int(match.group(1))


def fetch_listings() -> list[Listing]:
    with new_session() as session:
        listings: list[Listing] = []
        url: str | None = SEARCH_URL
        visited: set[str] = set()
        while url:
            if url in visited:
                raise RuntimeError("Vestim: pagination repeated a page before reaching the end")
            if len(visited) >= MAX_PAGES:
                raise RuntimeError(f"Vestim: pagination exceeds the limit of {MAX_PAGES} pages")
            if visited:
                time.sleep(PAGE_DELAY)
            visited.add(url)
            response = session.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            total = parse_total(response.text)
            page_listings, url = parse_page(response.text)
            if total and not page_listings:
                raise RuntimeError(f"Vestim: the site lists {total} homes but none could be read")
            listings.extend(page_listings)
        return listings


def _text(tag: Tag | None) -> str:
    return tag.get_text(" ", strip=True) if tag else ""
