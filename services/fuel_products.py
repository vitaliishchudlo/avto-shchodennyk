"""Module: fuel_products
Description: Fuel station product catalogs and name normalization for Ukrainian networks.
Edit this file manually to update product lists.
"""

# Slugs for callback_data (ASCII to avoid encoding issues)
STATION_SLUGS: dict[str, str] = {
    "ОККО": "okko",
    "WOG": "wog",
    "UPG": "upg",
    "УКРНАФТА": "ukrnafta",
    "SOCAR": "socar",
    "AMIC": "amic",
    "БРСМ": "brsm",
    "KLO": "klo",
}

SLUG_TO_STATION: dict[str, str] = {v: k for k, v in STATION_SLUGS.items()}

# Fuel stations shown in the main picker (Shell omitted — legacy entries only in FUEL_PRODUCTS)
POPULAR_STATIONS: list[str] = [
    "ОККО",
    "WOG",
    "UPG",
    "УКРНАФТА",
    "SOCAR",
    "AMIC",
    "БРСМ",
    "KLO",
]

FUEL_PRODUCTS: dict[str, dict[str, list[str]]] = {
    "ОККО": {
        "Бензин": ["Pulls 100", "Pulls 95", "A-95 Євро"],
        "Дизель": ["Pulls Diesel", "Pulls Diesel Арктика", "ДП Євро"],
        "Газ": ["Газ"],
    },
    "WOG": {
        "Бензин": ["100 Mustang", "95 Mustang", "95 Євро5-Е5"],
        "Дизель": ["ДП Mustang+", "ДП Євро5"],
        "Газ": ["Газ"],
        "Інше": ["AdBlue"],
    },
    "UPG": {
        "Бензин": ["upg100", "upg95", "А-95"],
        "Дизель": ["upgDIESEL", "EURO DIESEL", "DIESEL"],
        "Газ": ["Газ"],
    },
    "УКРНАФТА": {
        "Бензин": ["А-95 Energy", "А-95", "А-92"],
        "Дизель": ["ДП"],
        "Газ": ["Газ"],
    },
    "SOCAR": {
        "Бензин": ["NANO 100", "NANO 95", "A-95", "A-92"],
        "Дизель": ["DIESEL NANO Extro", "NANO ДП"],
        "Газ": ["LPG"],
        "Інше": ["AdBlue"],
    },
    "AMIC": {
        "Бензин": ["A95 Premium", "A95"],
        "Дизель": ["ДП Premium", "ДП"],
        "Газ": ["Газ"],
        "Інше": ["AdBlue"],
    },
    "БРСМ": {
        "Бензин": ["A-95", "A-92"],
        "Дизель": ["ДП"],
        "Газ": ["Газ PLUS", "Газ"],
    },
    "KLO": {
        "Бензин": ["F100", "Ventus 95", "Euro 95", "А-95", "А-92"],
        "Дизель": ["Ventus Diesel", "Euro Diesel"],
        "Газ": ["Gas LPG"],
    },
    # Legacy — not shown in the main picker; supports old entries and manual input
    "SHELL": {
        "Бензин": ["A-95", "A-95 Premium"],
        "Дизель": ["ДП"],
        "Газ": ["Газ"],
    },
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
    "amic": "AMIC",
    "амік": "AMIC",
    "брсм": "БРСМ",
    "брсм-нафта": "БРСМ",
    "brsm": "БРСМ",
    "klo": "KLO",
    "кло": "KLO",
    "shell": "SHELL",
    "шелл": "SHELL",
    "шел": "SHELL",
}


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


def get_products(station_name: str | None, fuel_type: str) -> list[str]:
    """Return product names for a fuel station and fuel type.

    Args:
        station_name: Fuel station name.
        fuel_type: Fuel category key (e.g. gasoline, diesel).

    Returns:
        Product list when the station is cataloged and the list is non-empty; otherwise [].
    """
    if not station_name or fuel_type == "Інше":
        return []

    canonical = normalize_station_name(station_name)
    if canonical not in FUEL_PRODUCTS:
        return []

    return FUEL_PRODUCTS[canonical].get(fuel_type, [])
