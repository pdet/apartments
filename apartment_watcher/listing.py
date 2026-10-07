from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Listing:
    source: str  # "Vestim" or "MVGM"
    listing_id: str  # stable id within the source
    url: str
    title: str  # as shown on the site, e.g. "Appartement Soerapatistraat 7"
    city: str
    status: str  # e.g. "Te huur", "Verhuurd"
    price: str | None = None  # as shown on the site, e.g. "€ 1.207,- /mnd"
    size_m2: int | None = None
    bedrooms: int | None = None
    available: str | None = None  # e.g. "Direct beschikbaar", "Per 12 Oktober 2026"

    @property
    def display_name(self) -> str:
        if self.city.casefold() in self.title.casefold():
            return self.title
        return f"{self.title}, {self.city}"

    @property
    def rent_eur(self) -> int | None:
        """Monthly rent in whole euros: "€ 1.207,- /mnd" -> 1207, "€ 1.583,00 / maand" -> 1583."""
        match = re.search(r"€\s*(\d[\d.]*)", self.price or "")
        return int(match.group(1).replace(".", "")) if match else None


def first_int(text: str | None) -> int | None:
    match = re.search(r"\d+", text or "")
    return int(match.group()) if match else None
