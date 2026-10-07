from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apartment_watcher import vestim

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_amsterdam_office_page():
    listings, next_url = vestim.parse_page((FIXTURES / "vestim_amsterdam.html").read_text())

    assert len(listings) == 10
    assert next_url is None
    by_id = {listing.listing_id: listing for listing in listings}

    lennepkade = by_id["amsterdam-jacob-van-lennepkade"]
    assert lennepkade.url == "https://www.vestim.nl/woning/amsterdam-jacob-van-lennepkade"
    assert lennepkade.title == "Amsterdam, Jacob van Lennepkade"
    assert lennepkade.city == "Amsterdam"
    assert lennepkade.status == "Te huur"
    assert lennepkade.price == "€ 1.583,00 / maand"
    assert lennepkade.size_m2 == 69
    assert lennepkade.bedrooms == 2
    assert lennepkade.available is None  # label is a tagline, not a date

    assert by_id["amsterdam-zuid-hollandstraat"].available == "Per 12 Oktober 2026"
    assert by_id["amstelveen-startbaan"].city == "Amstelveen"


def test_parse_follows_pagination():
    listings, next_url = vestim.parse_page((FIXTURES / "vestim_all_page1.html").read_text())

    assert len(listings) == 12
    assert next_url == "https://www.vestim.nl/woningen/page/2?status=for_rent"
    assert {listing.city for listing in listings} >= {"Amsterdam", "Den Haag", "Badhoevedorp"}


def test_parse_total():
    assert vestim.parse_total((FIXTURES / "vestim_amsterdam.html").read_text()) == 10
    assert vestim.parse_total((FIXTURES / "vestim_all_page1.html").read_text()) == 64
    assert vestim.parse_total('<div class="listing-tools-wrap"><div>0 woningen</div></div>') == 0
    with pytest.raises(RuntimeError):
        vestim.parse_total("<html>redesigned</html>")


def search_session(monkeypatch, pages):
    session = MagicMock()
    session.__enter__.return_value = session
    session.get.side_effect = [MagicMock(text=html) for html in pages]
    monkeypatch.setattr(vestim, "new_session", lambda: session)
    monkeypatch.setattr(vestim.time, "sleep", lambda seconds: None)
    return session


@pytest.mark.parametrize("later_page", [False, True])
@pytest.mark.parametrize(
    ("html", "error"),
    [
        ("<html>redesigned</html>", "result count not found"),
        ('<div class="listing-tools-wrap">3 woningen</div>', "none could be read"),
    ],
)
def test_fetch_rejects_unreadable_pages(monkeypatch, later_page, html, error):
    pages = [(FIXTURES / "vestim_all_page1.html").read_text(), html] if later_page else [html]
    session = search_session(monkeypatch, pages)
    with pytest.raises(RuntimeError, match=error):
        vestim.fetch_listings()
    assert session.get.call_count == (2 if later_page else 1)
    session.__exit__.assert_called_once()


@pytest.mark.parametrize("later_page", [False, True])
def test_fetch_accepts_verified_empty_page(monkeypatch, later_page):
    empty = '<div class="listing-tools-wrap">0 woningen</div>'
    pages = [(FIXTURES / "vestim_all_page1.html").read_text(), empty] if later_page else [empty]
    session = search_session(monkeypatch, pages)
    listings = vestim.fetch_listings()
    assert len(listings) == (12 if later_page else 0)
    assert session.get.call_count == len(pages)


def test_fetch_rejects_repeated_page(monkeypatch):
    page = (FIXTURES / "vestim_all_page1.html").read_text()
    session = search_session(monkeypatch, [page, page])
    with pytest.raises(RuntimeError, match="pagination repeated"):
        vestim.fetch_listings()
    assert session.get.call_count == 2


def test_fetch_rejects_pagination_above_limit(monkeypatch):
    session = search_session(monkeypatch, [(FIXTURES / "vestim_all_page1.html").read_text()])
    monkeypatch.setattr(vestim, "MAX_PAGES", 1)
    with pytest.raises(RuntimeError, match="pagination exceeds"):
        vestim.fetch_listings()
    session.get.assert_called_once()


def test_fetch_accepts_last_page_at_limit(monkeypatch):
    session = search_session(monkeypatch, [(FIXTURES / "vestim_amsterdam.html").read_text()])
    monkeypatch.setattr(vestim, "MAX_PAGES", 1)
    assert len(vestim.fetch_listings()) == 10
    session.get.assert_called_once()
