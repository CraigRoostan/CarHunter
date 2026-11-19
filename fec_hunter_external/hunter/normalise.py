"""Text handling: reading a vehicle out of a listing title, stripping contact details,
and deciding which configured search area a listing belongs to.

Nothing here guesses. When a field cannot be read from the listing it is left empty and
the dashboard flags the vehicle for review, rather than inventing a year or a model.
"""

import re
from html import unescape
from typing import Any, Dict, List, Optional

MAKES = [
    'Abarth', 'Alfa Romeo', 'Audi', 'BMW', 'Citroen', 'Citroën', 'Cupra', 'Dacia', 'DS',
    'Fiat', 'Ford', 'Honda', 'Hyundai', 'Isuzu', 'Jaguar', 'Jeep', 'Kia', 'Land Rover',
    'Lexus', 'Mazda', 'Mercedes-Benz', 'Mercedes', 'MG', 'Mini', 'Mitsubishi', 'Nissan',
    'Peugeot', 'Porsche', 'Renault', 'Saab', 'Seat', 'Skoda', 'Smart', 'Subaru', 'Suzuki',
    'Tesla', 'Toyota', 'Vauxhall', 'Volkswagen', 'Volvo', 'VW',
]

YEAR_RE = re.compile(r'\b(19[89]\d|20[0-2]\d)\b')
MILEAGE_RE = re.compile(r'\b(\d{1,3}(?:,\d{3})+|\d{3,6})\s*(?:miles|mile|mi|k)\b', re.IGNORECASE)
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
PHONE_RE = re.compile(r'(?:(?:\+44\s?\(?0?\)?|0)\s?\d{2,4}[\s.-]?\d{3,4}[\s.-]?\d{3,4})')
SPACE_RE = re.compile(r'\s+')
TAG_RE = re.compile(r'<[^>]+>')

# Spellings that would otherwise split the make from the model.
TITLE_FIXES = [
    (re.compile(r'mercedes[\s-]?benz', re.IGNORECASE), 'Mercedes-Benz'),
    (re.compile(r'land[\s-]?rover', re.IGNORECASE), 'Land Rover'),
    (re.compile(r'alfa[\s-]?romeo', re.IGNORECASE), 'Alfa Romeo'),
]


def clean(value: Any, limit: int = 300) -> str:
    if not isinstance(value, str):
        return ''
    return SPACE_RE.sub(' ', value).strip()[:limit]


def strip_tags(value: Any) -> str:
    """Text content of an HTML fragment, with tags removed and entities decoded."""
    if not isinstance(value, str):
        return ''
    return SPACE_RE.sub(' ', unescape(TAG_RE.sub(' ', value))).strip()


def parse_title(title: str) -> Dict[str, Any]:
    """Read make, model, year and mileage out of a title. Missing values stay absent."""
    text = clean(title, 300)
    if not text:
        return {}

    for pattern, replacement in TITLE_FIXES:
        text = pattern.sub(replacement, text)

    result: Dict[str, Any] = {}

    year_match = YEAR_RE.search(text)
    if year_match:
        result['year'] = int(year_match.group(1))

    mileage_match = MILEAGE_RE.search(text)
    if mileage_match:
        digits = re.sub(r'\D', '', mileage_match.group(1))
        if digits:
            value = int(digits)
            if value < 1000 and re.search(r'\d\s*k\b', mileage_match.group(0), re.IGNORECASE):
                value *= 1000
            if 1000 <= value <= 400000:
                result['mileage'] = value

    best_make = ''
    best_end = -1
    for candidate in MAKES:
        match = re.search(r'\b' + re.escape(candidate) + r'\b', text, re.IGNORECASE)
        if match and (best_end == -1 or match.start() < best_end):
            best_make = candidate
            best_end = match.end()
    if best_make:
        result['make'] = best_make
        after = text[best_end:].strip(' -|,./')
        if after:
            token = after.split()[0].strip(' -|,./')
            if token and not token.isdigit():
                result['model'] = token[:40]

    return result


def redact_contact(text: str, limit: int = 4000) -> str:
    """Remove phone numbers and email addresses. They are never stored or sent."""
    value = clean(text, limit)
    if not value:
        return ''
    value = EMAIL_RE.sub('[contact removed]', value)
    value = PHONE_RE.sub('[contact removed]', value)
    return value


# Towns that belong to a wider configured area. Without these, a car in Chatham would
# not be recognised as Medway.
AREA_ALIASES = {
    'medway': ['chatham', 'rochester', 'gillingham', 'strood', 'rainham'],
    'bromley': ['beckenham', 'west wickham', 'petts wood'],
    'dartford': ['swanley', 'bexleyheath', 'erith'],
    'tunbridge wells': ['royal tunbridge wells', 'tonbridge'],
    'maidstone': ['west malling', 'snodland', 'larkfield'],
    'canterbury': ['whitstable', 'herne bay'],
    'sevenoaks': ['westerham', 'otford'],
    'gravesend': ['northfleet', 'ebbsfleet', 'meopham'],
    'orpington': ['st mary cray', 'farnborough'],
    'ashford': ['tenterden', 'charing'],
}


def match_area(location: str, areas: List[Dict[str, Any]]) -> Optional[str]:
    """Which configured area a listing's location text falls in, if any."""
    text = (location or '').lower()
    if not text:
        return None

    for area in areas:
        name = str(area.get('name') or '').strip()
        if name and name.lower() in text:
            return name

    for area in areas:
        name = str(area.get('name') or '').strip().lower()
        for alias in AREA_ALIASES.get(name, []):
            if alias in text:
                return str(area.get('name')).strip()

    return None