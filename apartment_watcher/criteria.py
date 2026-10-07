"""Which listings are worth applying to automatically."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .listing import Listing

# MVGM's income rule: yearly gross income of at least this many times the monthly base rent.
INCOME_MULTIPLIER_SINGLE = 45
INCOME_MULTIPLIER_HOUSEHOLD = 60  # two or more people, combined income


@dataclass(frozen=True)
class Criteria:
    max_rent: int | None = None
    min_size_m2: int | None = None
    gross_yearly_income: int | None = None
    household_size: int = 1

    @classmethod
    def from_env(cls) -> Criteria:
        return cls(
            max_rent=_env_int("MAX_RENT"),
            min_size_m2=_env_int("MIN_SIZE_M2"),
            gross_yearly_income=_env_int("GROSS_YEARLY_INCOME"),
            household_size=_env_int("HOUSEHOLD_SIZE") or 1,
        )

    @property
    def income_multiplier(self) -> int:
        return INCOME_MULTIPLIER_SINGLE if self.household_size <= 1 else INCOME_MULTIPLIER_HOUSEHOLD

    def failures(self, listing: Listing) -> list[str]:
        """Reasons not to apply; empty if the listing fits. Unknown values count as not fitting."""
        reasons = []
        rent = listing.rent_eur
        if rent is None and (self.max_rent is not None or self.gross_yearly_income is not None):
            reasons.append("rent unknown")
        if self.max_rent is not None and rent is not None and rent > self.max_rent:
            reasons.append(f"rent {_eur(rent)} > max {_eur(self.max_rent)}")
        if self.min_size_m2 is not None:
            if listing.size_m2 is None:
                reasons.append("size unknown")
            elif listing.size_m2 < self.min_size_m2:
                reasons.append(f"{listing.size_m2} m² < min {self.min_size_m2} m²")
        if self.gross_yearly_income is not None and rent is not None:
            required = self.income_multiplier * rent
            if self.gross_yearly_income < required:
                reasons.append(
                    f"income {_eur(self.gross_yearly_income)} < {self.income_multiplier} × {_eur(rent)}"
                    f" = {_eur(required)}"
                )
        return reasons


def _eur(amount: int) -> str:
    return f"€ {amount:,}".replace(",", ".")


def _env_int(name: str) -> int | None:
    value = os.environ.get(name, "").strip()
    return int(value) if value else None
