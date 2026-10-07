from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apartment_watcher import mvgm, mvgm_apply
from apartment_watcher.applying import LoginError

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "mvgm_amsterdam_page1.html").read_text()


def test_parse_search_results_page():
    listings, last_page = mvgm.parse_page(PAGE)

    assert len(listings) == 10
    assert last_page == 25
    by_id = {listing.listing_id: listing for listing in listings}

    studio = by_id["85d07fdb8d4a4de7a0bf2fe9c5e25ec0"]
    assert studio.url == (
        "https://ikwilhuren.nu/object/amsterdam-1018pn-7-soerapatistraat-85d07fdb8d4a4de7a0bf2fe9c5e25ec0/"
    )
    assert studio.title == "Appartement Soerapatistraat 7"
    assert studio.city == "Amsterdam"
    assert studio.status == "Te huur"
    assert studio.price == "€ 1.207,- /mnd"
    assert studio.size_m2 == 36
    assert studio.bedrooms is None
    assert studio.available == "Direct beschikbaar"

    molenwerf = by_id["e263a4271af8e92804c481b125210f3d"]
    assert molenwerf.size_m2 == 79
    assert molenwerf.bedrooms == 2
    assert molenwerf.available == "Beschikbaar vanaf 01-11-2026"


@pytest.mark.parametrize(
    ("location", "city"),
    [
        ("1018PN Amsterdam - 2Km.", "Amsterdam"),
        ("1187AB Amstelveen - 7Km.", "Amstelveen"),
        ("1115AB Amsterdam-Duivendrecht - 5Km.", "Amsterdam-Duivendrecht"),
        ("2405VV Alphen aan den Rijn - 30Km.", "Alphen aan den Rijn"),
        ("Amsterdam", ""),  # no postcode: unexpected format
    ],
)
def test_parse_city(location, city):
    assert mvgm.parse_city(location) == city


def test_parse_csrf_token():
    assert len(mvgm.parse_csrf_token(PAGE)) == 40


def test_search_applied():
    assert mvgm.search_applied(PAGE)
    assert not mvgm.search_applied((FIXTURES / "mvgm_unfiltered_page1.html").read_text())


def response(text="", data=None):
    result = MagicMock(text=text)
    result.json.return_value = data
    return result


def test_open_session_refreshes_csrf_after_ajax_cookie_creation(monkeypatch):
    session = MagicMock()
    session.get.side_effect = [response('<input name="_token" value="initial">'), response('<input name="_token" value="persisted">')]
    session.post.return_value = response(data={"results": [{"id": "city", "text": mvgm.CITY_LABEL}]})
    monkeypatch.setattr(mvgm, "new_session", lambda: session)
    opened, token = mvgm.open_session()
    assert opened is session and token == "persisted"
    assert session.post.call_args.kwargs["headers"]["X-CSRF-TOKEN"] == "initial"
    assert [call[0] for call in session.method_calls] == ["get", "post", "get"]
    session.close.assert_not_called()


def test_open_session_closes_on_failure(monkeypatch):
    session = MagicMock()
    session.get.return_value = response('<input name="_token" value="">')
    monkeypatch.setattr(mvgm, "new_session", lambda: session)
    with pytest.raises(RuntimeError, match="CSRF"):
        mvgm.open_session()
    session.close.assert_called_once()


def test_lost_search_filter_on_later_page_is_rejected(monkeypatch):
    session = MagicMock()
    session.post.side_effect = [
        response(data={"results": [{"id": "city", "text": mvgm.CITY_LABEL}]}),
        response(data={"lat": 52, "lng": 4}), response(PAGE),
    ]
    session.get.return_value = response((FIXTURES / "mvgm_unfiltered_page1.html").read_text())
    monkeypatch.setattr(mvgm, "open_session", lambda: (session, "token"))
    monkeypatch.setattr(mvgm.time, "sleep", lambda seconds: None)
    with pytest.raises(RuntimeError, match="filter was lost"):
        mvgm.fetch_listings()
    assert session.post.call_args.kwargs["data"]["selAfstand"] == 20
    session.__exit__.assert_called_once()


@pytest.mark.parametrize("html", ["", "{}", "<h1>Try again</h1>", PAGE, '<nav id="navbar-account"><a href="https://ikwilhuren.nu/login?next=/aanbod/">Login</a></nav>'])
def test_anonymous_or_unexpected_html_is_not_a_verified_login(html):
    assert not mvgm_apply.is_logged_in(html)


def test_login_uses_form_token_and_checks_authenticated_search_page(monkeypatch):
    session = MagicMock()
    session.get.side_effect = [
        response('<input name="_token" value="login-token">'),
        response('<nav id="navbar-account"><a href="/">Account</a></nav>'),
    ]
    session.post.return_value = response("{}")
    monkeypatch.setattr(mvgm, "open_session", lambda: (session, "search-token"))
    applicant = mvgm_apply.MvgmApplicant("account@example.com", "password")
    applicant.login()
    assert session.post.call_args.kwargs["data"]["_token"] == "login-token"
    assert session.get.call_args.args == (mvgm.SEARCH_URL,)
    assert applicant.session is session
    applicant.close()
    session.close.assert_called_once()


def test_failed_relogin_discards_old_session(monkeypatch):
    old_session, session = MagicMock(), MagicMock()
    session.get.side_effect = [response('<input name="_token" value="token">'), response(PAGE)]
    session.post.return_value = response()
    monkeypatch.setattr(mvgm, "open_session", lambda: (session, "token"))
    applicant = mvgm_apply.MvgmApplicant("account@example.com", "password")
    applicant.session = old_session
    with pytest.raises(LoginError):
        applicant.login()
    assert applicant.session is None
    old_session.close.assert_called_once()
    session.close.assert_called_once()


def test_live_apply_stays_unimplemented():
    applicant = mvgm_apply.MvgmApplicant("account@example.com", "password")
    with pytest.raises(NotImplementedError):
        applicant.apply(None)


def test_parse_total():
    assert mvgm.parse_total(PAGE) == 243
    assert mvgm.parse_total("<span>0</span> huurwoningen gevonden") == 0
    with pytest.raises(RuntimeError):
        mvgm.parse_total("<html>redesigned</html>")


def search_session(monkeypatch, first_page, later_page=""):
    session = MagicMock()
    session.post.side_effect = [
        response(data={"results": [{"id": "city", "text": mvgm.CITY_LABEL}]}),
        response(data={"lat": 52, "lng": 4}),
        response(first_page),
    ]
    session.get.return_value = response(later_page)
    monkeypatch.setattr(mvgm, "open_session", lambda: (session, "token"))
    monkeypatch.setattr(mvgm.time, "sleep", lambda seconds: None)
    return session


@pytest.mark.parametrize("later_page", [False, True])
@pytest.mark.parametrize(
    ("html", "error"),
    [
        ("<html>redesigned</html>", "result count not found"),
        ("<span>3</span> huurwoningen gevonden", "none could be read"),
    ],
)
def test_fetch_rejects_unreadable_pages(monkeypatch, later_page, html, error):
    session = search_session(monkeypatch, PAGE if later_page else html, html)
    with pytest.raises(RuntimeError, match=error):
        mvgm.fetch_listings()
    assert session.get.call_count == int(later_page)
    session.__exit__.assert_called_once()


@pytest.mark.parametrize("later_page", [False, True])
def test_fetch_accepts_verified_empty_page(monkeypatch, later_page):
    empty = "<span>0</span> huurwoningen gevonden"
    session = search_session(monkeypatch, PAGE if later_page else empty, empty)
    listings = mvgm.fetch_listings()
    assert len(listings) == (10 if later_page else 0)
    assert session.get.call_count == int(later_page)


def test_fetch_rejects_pagination_above_limit(monkeypatch):
    session = search_session(monkeypatch, PAGE)
    monkeypatch.setattr(mvgm, "MAX_PAGES", 2)
    with pytest.raises(RuntimeError, match="pagination exceeds"):
        mvgm.fetch_listings()
    session.get.assert_not_called()
