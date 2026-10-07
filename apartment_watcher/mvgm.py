"""Scrape MVGM's rental portal using its session-based Amsterdam search."""

from __future__ import annotations

import json
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from .listing import Listing, first_int
from .session import PAGE_DELAY, TIMEOUT, new_session

SOURCE = "MVGM"
BASE_URL = "https://ikwilhuren.nu"
SEARCH_URL = f"{BASE_URL}/aanbod/"
CITY_QUERY = "Amsterdam"
CITY_LABEL = "Amsterdam, Amsterdam, Noord-Holland"  # the woonplaats, not e.g. Nieuw-Amsterdam
# A 20 km radius includes Amsterdam's outer districts; the watcher filters by city afterwards.
SEARCH_RADIUS_KM = 20
MAX_PAGES = 100

_ID_RE = re.compile(r"-([0-9a-f]{32})/?$")
# e.g. "1018PN Amsterdam - 2Km." or "2405VV Alphen aan den Rijn - 30Km."
_LOCATION_RE = re.compile(r"^(?:\d{4}\s?[A-Z]{2}\s+)?(.+?)(?:\s+-\s+[\d.,]+\s*km\.?)?$", re.IGNORECASE)
_PAGE_RE = re.compile(r"[?&]page=(\d+)")
# Cards only show a distance ("- 2Km.") when a location search is active.
_DISTANCE_RE = re.compile(r"\s-\s[\d.,]+\s*Km\.")


def parse_page(html: str) -> tuple[list[Listing], int]:
    """Return the listings on an /aanbod/ page and the number of the last page."""
    soup = BeautifulSoup(html, "html.parser")
    listings = []
    for card in soup.select("div.card-woning"):
        link = card.select_one("a.stretched-link[href]")
        if link is None:
            continue
        url = urljoin(BASE_URL, link["href"])
        id_match = _ID_RE.search(link["href"])
        title_span = link.find_parent("span")
        location = title_span.find_next_sibling("span") if title_span else None
        calendar = card.select_one("i.fa-calendar")
        availability = calendar.find_parent("span", class_="d-flex") if calendar else None
        status_dot = card.select_one(".status-dot")
        details = [_text(span) for span in card.select(".dotted-spans > span")]
        listings.append(
            Listing(
                source=SOURCE,
                listing_id=id_match.group(1) if id_match else url,
                url=url,
                title=_text(link),
                city=parse_city(_text(location)),
                status=_text(status_dot.parent) if status_dot else "",
                price=next((d for d in details if "€" in d), None),
                size_m2=first_int(next((d for d in details if "m2" in d.replace(" ", "").replace("²", "2")), None)),
                bedrooms=first_int(next((d for d in details if "slaapkamer" in d.lower()), None)),
                available=_text(availability) or None,
            )
        )
    pages = [int(m.group(1)) for a in soup.select("a.page-link[href]") if (m := _PAGE_RE.search(a["href"]))]
    return listings, max(pages, default=1)


def parse_city(location: str) -> str:
    match = _LOCATION_RE.match(location.strip())
    return match.group(1).strip() if match else location.strip()


def search_applied(html: str) -> bool:
    return _DISTANCE_RE.search(html) is not None


def parse_csrf_token(html: str) -> str:
    token = BeautifulSoup(html, "html.parser").select_one('input[name="_token"][value]')
    if token is None or not token["value"].strip():
        raise RuntimeError("MVGM: CSRF token not found on the page")
    return token["value"]


def open_session() -> tuple[requests.Session, str]:
    """Return a session whose cookie is persisted by the site, plus its CSRF token."""
    session = new_session()
    try:
        response = session.get(SEARCH_URL, timeout=TIMEOUT)
        response.raise_for_status()
        # The cookie is only created by an AJAX call; the address lookup is a cheap one.
        _lookup_location(session, parse_csrf_token(response.text))
        response = session.get(SEARCH_URL, timeout=TIMEOUT)
        response.raise_for_status()
        return session, parse_csrf_token(response.text)
    except BaseException:
        session.close()
        raise


def _lookup_location(session: requests.Session, token: str) -> str:
    """Resolve Amsterdam through the address autocomplete, like the site's search box does."""
    response = session.post(
        f"{BASE_URL}/aanbod/geo/adressen/",
        data={"q": CITY_QUERY, "typefilter": "(gemeente OR woonplaats)", "page": 1},
        headers=_ajax_headers(token),
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    location_id = next((r["id"] for r in response.json().get("results", []) if r.get("text") == CITY_LABEL), None)
    if location_id is None:
        raise RuntimeError(f"MVGM: location {CITY_LABEL!r} not found in address lookup")
    return location_id


def _ajax_headers(token: str) -> dict[str, str]:
    return {"X-CSRF-TOKEN": token, "X-Requested-With": "XMLHttpRequest"}


def fetch_listings() -> list[Listing]:
    session, token = open_session()
    with session:
        location_id = _lookup_location(session, token)
        response = session.post(
            f"{BASE_URL}/aanbod/geo/adres/",
            data={"locatieid": location_id},
            headers=_ajax_headers(token),
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        response = session.post(
            SEARCH_URL,
            data={
                "_token": token,
                "postrequest": "doeZoek",
                "objSearch": json.dumps(response.json()),
                "selAdres": location_id,
                "selAfstand": SEARCH_RADIUS_KM,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        listings, last_page = parse_page(response.text)
        if listings and not search_applied(response.text):
            raise RuntimeError("MVGM: the Amsterdam search filter was not applied (got the unfiltered list)")

        for page in range(2, min(last_page, MAX_PAGES) + 1):
            time.sleep(PAGE_DELAY)
            response = session.get(SEARCH_URL, params={"page": page}, timeout=TIMEOUT)
            response.raise_for_status()
            page_listings, _ = parse_page(response.text)
            if not page_listings:
                break
            if not search_applied(response.text):
                raise RuntimeError("MVGM: the Amsterdam search filter was lost during pagination")
            listings.extend(page_listings)

        # Listings can shift between pages while we paginate; keep the first occurrence.
        unique: dict[str, Listing] = {}
        for listing in listings:
            unique.setdefault(listing.listing_id, listing)
        return list(unique.values())


def _text(tag: Tag | None) -> str:
    return tag.get_text(" ", strip=True) if tag else ""
