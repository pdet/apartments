from pathlib import Path

import pytest

from apartment_watcher import mvgm

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
        ("Amsterdam", "Amsterdam"),
    ],
)
def test_parse_city(location, city):
    assert mvgm.parse_city(location) == city


def test_parse_csrf_token():
    assert len(mvgm.parse_csrf_token(PAGE)) == 40


def test_search_applied():
    assert mvgm.search_applied(PAGE)
    assert not mvgm.search_applied((FIXTURES / "mvgm_unfiltered_page1.html").read_text())
