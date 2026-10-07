import pytest

from apartment_watcher.criteria import Criteria
from apartment_watcher.listing import Listing


def make_listing(price="€ 1.500,- /mnd", size_m2=60):
    return Listing("MVGM", "1", "https://example.com/1", "Appartement Straat 1", "Amsterdam", "Te huur", price, size_m2)


@pytest.mark.parametrize(
    ("price", "rent"),
    [("€ 1.207,- /mnd", 1207), ("€ 1.583,00 / maand", 1583), ("€ 976,00 / maand", 976), (None, None)],
)
def test_rent_eur(price, rent):
    assert make_listing(price=price).rent_eur == rent


def test_no_criteria_fits_everything():
    assert Criteria().failures(make_listing(price=None, size_m2=None)) == []


def test_max_rent_and_min_size():
    criteria = Criteria(max_rent=1400, min_size_m2=70)
    assert criteria.failures(make_listing()) == ["rent € 1.500 > max € 1.400", "60 m² < min 70 m²"]
    assert criteria.failures(make_listing(price="€ 1.400,- /mnd", size_m2=70)) == []


def test_unknown_values_do_not_fit():
    criteria = Criteria(max_rent=1400, min_size_m2=40)
    assert criteria.failures(make_listing(price=None, size_m2=None)) == ["rent unknown", "size unknown"]


def test_income_rule_depends_on_household_size():
    assert Criteria(gross_yearly_income=67_500).failures(make_listing()) == []
    assert Criteria(gross_yearly_income=67_499).failures(make_listing()) == [
        "income € 67.499 < 45 × € 1.500 = € 67.500"
    ]
    assert Criteria(gross_yearly_income=80_000, household_size=2).failures(make_listing()) == [
        "income € 80.000 < 60 × € 1.500 = € 90.000"
    ]
