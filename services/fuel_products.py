"""Module: fuel_products
Description: Fuel station product catalogs, name normalization, and matching of
free-form fuel names (receipts, imports) onto the unified catalog names.
Edit this file manually to update product lists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Slugs for callback_data (ASCII to avoid encoding issues)
STATION_SLUGS: dict[str, str] = {
    "ОККО": "okko",
    "WOG": "wog",
    "UPG": "upg",
    "УКРНАФТА": "ukrnafta",
    "SOCAR": "socar",
    "БРСМ": "brsm",
}

SLUG_TO_STATION: dict[str, str] = {v: k for k, v in STATION_SLUGS.items()}

# Fuel stations shown in the main picker (Shell omitted — legacy entries only in FUEL_PRODUCTS)
POPULAR_STATIONS: list[str] = [
    "ОККО",
    "WOG",
    "UPG",
    "УКРНАФТА",
    "SOCAR",
    "БРСМ",
]

# Unified fuel names. Conventions: octane grades as Cyrillic "А-95", diesel as "ДП",
# LPG as "Газ"; branded premium fuels keep the network's own name.
FUEL_PRODUCTS: dict[str, dict[str, list[str]]] = {
    "ОККО": {
        "Бензин": ["Pulls 100", "Pulls 95", "А-95 Євро"],
        "Дизель": ["Pulls Diesel", "ДП Євро"],
        "Газ": ["Газ"],
    },
    "WOG": {
        "Бензин": ["100 Mustang", "95 Mustang", "А-95 Євро"],
        "Дизель": ["ДП Mustang+", "ДП Євро"],
        "Газ": ["Газ"],
        "Інше": ["AdBlue"],
    },
    "UPG": {
        "Бензин": ["upg100", "upg95", "А-95"],
        "Дизель": ["upgDIESEL", "ДП"],
        "Газ": ["Газ"],
    },
    "УКРНАФТА": {
        "Бензин": ["А-95 Energy", "А-95", "А-92"],
        "Дизель": ["ДП"],
        "Газ": ["Газ"],
    },
    "SOCAR": {
        "Бензин": ["NANO 100", "NANO 95", "А-95", "А-92"],
        "Дизель": ["NANO Extro ДП", "NANO ДП"],
        "Газ": ["Газ"],
        "Інше": ["AdBlue"],
    },
    "БРСМ": {
        "Бензин": ["А-95", "А-92"],
        "Дизель": ["ДП"],
        "Газ": ["Газ PLUS", "Газ"],
    },
    # Legacy — not shown in the main picker; supports old entries and manual input
    "SHELL": {
        "Бензин": ["А-95", "А-95 Premium"],
        "Дизель": ["ДП"],
        "Газ": ["Газ"],
    },
}

# Catalog for stations without their own list (manual "other station", unknown receipts)
GENERIC_PRODUCTS: dict[str, list[str]] = {
    "Бензин": ["А-100", "А-98", "А-95", "А-92"],
    "Дизель": ["ДП"],
    "Газ": ["Газ"],
}

_STATION_ALIASES: dict[str, str] = {
    "окко": "ОККО",
    "okko": "ОККО",
    "вог": "WOG",
    "wog": "WOG",
    "вогг": "WOG",
    "upg": "UPG",
    "юпіджі": "UPG",
    "укрнафта": "УКРНАФТА",
    "ukrnafta": "УКРНАФТА",
    "socar": "SOCAR",
    "сокар": "SOCAR",
    "брсм": "БРСМ",
    "брсм-нафта": "БРСМ",
    "brsm": "БРСМ",
    "shell": "SHELL",
    "шелл": "SHELL",
    "шел": "SHELL",
}

# Brand / grade markers that distinguish products of the same type and octane.
# Each alias maps to one token; generic words like "євро" / "euro" are deliberately absent.
_PRODUCT_TOKENS: dict[str, str] = {
    "pulls": "pulls",
    "пулс": "pulls",
    "пулльс": "pulls",
    "mustang": "mustang",
    "мустанг": "mustang",
    "nano": "nano",
    "нано": "nano",
    "extro": "extro",
    "екстро": "extro",
    "energy": "energy",
    "енерджі": "energy",
    "upg": "upg",
    "premium": "premium",
    "преміум": "premium",
    "plus": "plus",
    "плюс": "plus",
    "+": "plus",
    "adblue": "adblue",
}

_DIESEL_MARKERS = ("дп", "diesel", "дизел", "д/п", "дт")
_GAS_MARKERS = ("газ", "lpg", "пропан", "суг", "autogas")
_PETROL_MARKERS = ("бенз", "petrol", "gasoline")
_OCTANE_RE = re.compile(r"(?<!\d)(92|95|98|100)(?!\d)")
# Latin letters that look like Cyrillic ones, so "A-95" and "А-95" compare equal
_LOOKALIKES = str.maketrans("aceiopxyk", "асеіорхук")


def normalize_station_name(name: str) -> str:
    """Normalize a fuel station name using aliases and FUEL_PRODUCTS canonical keys.

    Args:
        name: Raw station name from user input or storage.

    Returns:
        Canonical station name when recognized; otherwise the stripped input.
    """
    key = name.strip().lower()
    if key in _STATION_ALIASES:
        return _STATION_ALIASES[key]

    stripped = name.strip()
    for station in FUEL_PRODUCTS:
        if station.upper() == stripped.upper():
            return station
    for station in POPULAR_STATIONS:
        if station.upper() == stripped.upper():
            return station

    return stripped


def has_product_catalog(station_name: str | None) -> bool:
    """Return whether the fuel station has a defined product catalog.

    Args:
        station_name: Station name to look up.

    Returns:
        True when the normalized name exists in FUEL_PRODUCTS.
    """
    if not station_name:
        return False
    return normalize_station_name(station_name) in FUEL_PRODUCTS


def _station_catalog(station_name: str | None) -> dict[str, list[str]]:
    """Return the station's catalog, or the generic one for unknown stations."""
    if station_name:
        canonical = normalize_station_name(station_name)
        if canonical in FUEL_PRODUCTS:
            return FUEL_PRODUCTS[canonical]
    return GENERIC_PRODUCTS


def get_products(station_name: str | None, fuel_type: str) -> list[str]:
    """Return product names for a fuel station and fuel type.

    Args:
        station_name: Fuel station name; unknown or missing stations use GENERIC_PRODUCTS.
        fuel_type: Fuel category key (e.g. gasoline, diesel).

    Returns:
        Product list for the category; [] for "Інше" or an empty category.
    """
    if fuel_type == "Інше":
        return []
    return _station_catalog(station_name).get(fuel_type, [])


def get_all_products(station_name: str | None) -> list[str]:
    """Return every product of the station's catalog (generic for unknown stations)."""
    return [p for products in _station_catalog(station_name).values() for p in products]


@dataclass(frozen=True)
class _FuelSignature:
    category: str | None
    octane: str | None
    tokens: frozenset[str]


def _fold(text: str) -> str:
    return " ".join(text.lower().translate(_LOOKALIKES).split())


def _signature(name: str) -> _FuelSignature:
    """Extract fuel category, octane, and brand tokens from a free-form fuel name."""
    raw = name.lower()
    folded = _fold(name)
    tokens = {
        token
        for alias, token in _PRODUCT_TOKENS.items()
        if alias in raw or alias.translate(_LOOKALIKES) in folded
    }
    if "adblue" in tokens:
        return _FuelSignature("Інше", None, frozenset(tokens))

    def has(markers: tuple[str, ...]) -> bool:
        # Latin markers must be checked on the raw text, Cyrillic ones on the folded text
        return any(marker in raw or marker in folded for marker in markers)

    octane_match = _OCTANE_RE.search(raw)
    octane = octane_match.group(1) if octane_match else None
    if has(_GAS_MARKERS):
        category = "Газ"
    elif has(_DIESEL_MARKERS):
        category = "Дизель"
    elif octane or has(_PETROL_MARKERS):
        category = "Бензин"
    else:
        category = None
    return _FuelSignature(category, octane, frozenset(tokens))


def match_fuel_product(station_name: str | None, raw_name: str | None) -> str | None:
    """Map a free-form fuel name (e.g. from a receipt) onto the station's catalog name.

    Rules: same category; same octane for petrol; the product must carry every brand
    token of the raw name (Pulls, Mustang, …), and among those the one with the fewest
    extra tokens wins. Ambiguous or unknown names return None.

    Example: ("ОККО", "Бенз.авто А-95-Євро5-E10") -> "А-95 Євро".
    """
    if not raw_name or not raw_name.strip():
        return None
    products = get_all_products(station_name)

    folded = _fold(raw_name)
    for product in products:
        if _fold(product) == folded:
            return product

    wanted = _signature(raw_name)
    if wanted.category is None:
        return None

    candidates: list[tuple[int, str]] = []
    for product in products:
        sig = _signature(product)
        if sig.category != wanted.category:
            continue
        if wanted.category == "Бензин" and sig.octane != wanted.octane:
            continue
        if not wanted.tokens <= sig.tokens:
            continue
        candidates.append((len(sig.tokens - wanted.tokens), product))

    if not candidates:
        return None
    candidates.sort()
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return None
    return candidates[0][1]


def catalog_prompt_text() -> str:
    """Render the catalogs for AI prompts, one station per line."""
    lines = []
    for station in POPULAR_STATIONS:
        names = ", ".join(get_all_products(station))
        lines.append(f"- {station}: {names}")
    lines.append(f"- інші АЗС: {', '.join(get_all_products(None))}")
    return "\n".join(lines)
