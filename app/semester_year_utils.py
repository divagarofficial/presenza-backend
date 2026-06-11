from __future__ import annotations

from typing import Dict


YEAR_ADVANCE_MAP: Dict[str, str] = {
    "I": "II",
    "II": "III",
    "III": "IV",
    "IV": "IV",  # keep final year at IV
}


def advance_year_value(year: str) -> str:
    """Advance academic year by +1.

    Inputs are expected to be in roman form: I, II, III, IV.
    Unknown values are returned as-is.
    """
    if year is None:
        return year
    year = str(year).strip()
    return YEAR_ADVANCE_MAP.get(year, year)

