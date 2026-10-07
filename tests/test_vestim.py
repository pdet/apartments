from pathlib import Path

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
