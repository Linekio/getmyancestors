
"""Convert FamilySearch dates into GEDCOM 5.5.1 dates."""

import re
import unicodedata
from datetime import date


MONTH_NAMES = (
    ("JAN", "JANUARY", "ENERO", "XANEIRO", "JANEIRO"),
    ("FEB", "FEBRUARY", "FEBRERO", "FEBREIRO", "FEVEREIRO"),
    ("MAR", "MARCH", "MARZO", "MARÇO"),
    ("APR", "APRIL", "ABR", "ABRIL"),
    ("MAY", "MAYO", "MAIO"),
    ("JUN", "JUNE", "JUNIO", "XUÑO", "JUNHO"),
    ("JUL", "JULY", "JULIO", "XULLO", "JULHO"),
    ("AUG", "AUGUST", "AGOSTO"),
    ("SEP", "SEPT", "SEPTEMBER", "SEPTIEMBRE", "SETIEMBRE", "SETEMBRO"),
    ("OCT", "OCTOBER", "OCTUBRE", "OUTUBRO"),
    ("NOV", "NOVEMBER", "NOVIEMBRE", "NOVEMBRO"),
    ("DEC", "DECEMBER", "DICIEMBRE", "DECEMBRO", "DEZEMBRO"),
)

GEDCOM_MONTHS = tuple(names[0] for names in MONTH_NAMES)


def _key(value):
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )
    return value.upper().strip(".,")


MONTH_LOOKUP = {
    _key(name): number
    for number, names in enumerate(MONTH_NAMES, 1)
    for name in names
}


def _calendar_date(year, month=None, day=None):
    """Return a valid GEDCOM Gregorian date or None."""
    try:
        year = int(year)

        if not 1 <= year <= 9999:
            return None

        if month is None:
            return str(year)

        month = int(month)
        date(year, month, int(day or 1))

        if day is None:
            return "{} {}".format(
                GEDCOM_MONTHS[month - 1], year
            )

        return "{:02d} {} {}".format(
            int(day), GEDCOM_MONTHS[month - 1], year
        )
    except (ValueError, TypeError, OverflowError):
        return None


def _simple_date(text):
    """Parse dates whose order is unambiguous."""
    text = text.strip()

    if re.fullmatch(r"\d{3,4}", text):
        return _calendar_date(text)

    match = re.fullmatch(
        r"(\d{4})-(\d{2})-(\d{2})", text
    )
    if match:
        return _calendar_date(*match.groups())

    match = re.fullmatch(
        r"(\d{1,2})/(\d{1,2})/(\d{3,4})", text
    )
    if match:
        first, second, year = map(int, match.groups())

        if first > 12 and second <= 12:
            return _calendar_date(year, second, first)

        if second > 12 and first <= 12:
            return _calendar_date(year, first, second)

        return None

    match = re.fullmatch(
        r"(\d{1,2})\s+(?:de\s+)?([^\d\s]+)"
        r"\s+(?:de\s+)?(\d{3,4})",
        text,
        re.IGNORECASE,
    )
    if match:
        day, month_name, year = match.groups()
        month = MONTH_LOOKUP.get(_key(month_name))

        if month:
            return _calendar_date(year, month, day)

    match = re.fullmatch(
        r"([^\d\s]+)\s+(\d{1,2}),?\s+(\d{3,4})",
        text,
        re.IGNORECASE,
    )
    if match:
        month_name, day, year = match.groups()
        month = MONTH_LOOKUP.get(_key(month_name))

        if month:
            return _calendar_date(year, month, day)

    match = re.fullmatch(
        r"([^\d\s]+)\s+(?:de\s+)?(\d{3,4})",
        text,
        re.IGNORECASE,
    )
    if match:
        month_name, year = match.groups()
        month = MONTH_LOOKUP.get(_key(month_name))

        if month:
            return _calendar_date(year, month)

    return None


def _formal_simple_date(formal):
    """Convert a simple GEDCOM X date, including an approximation marker.

    Complex forms (ranges, BCE years, durations and times) must not be
    treated as exact Gregorian dates.
    """
    if not isinstance(formal, str):
        return None

    match = re.fullmatch(
        r"(A)?\+(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?",
        formal,
    )
    if not match:
        return None

    approximate, year, month, day = match.groups()
    converted = _calendar_date(year, month, day)
    if converted is None:
        return None

    return "ABT " + converted if approximate else converted


def _formal_fallback(original, text, formal):
    """Prefer standardized dates without losing the original date phrase.

    Do not reinterpret a conflicting year or an ambiguous numeric date.
    Unsupported date ranges stay as original text rather than being
    converted to an incorrectly precise single date.
    """
    converted = _formal_simple_date(formal)
    if converted is None:
        return _fallback(original, text)

    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{3,4}", text):
        return _fallback(original, text)

    # An otherwise recognizable ISO or named-month date failed validation.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return _fallback(original, text)
    named_date = re.fullmatch(
        r"(\d{1,2})\s+(?:de\s+)?([^\d\s]+)\s+(?:de\s+)?(\d{3,4})",
        text,
        re.IGNORECASE,
    )
    if named_date and MONTH_LOOKUP.get(_key(named_date.group(2))):
        return _fallback(original, text)

    years = set(re.findall(r"(?<!\d)\d{4}(?!\d)", text))
    formal_year = re.search(r"\+(\d{4})", formal).group(1)
    if years and years != {formal_year}:
        return _fallback(original, text)

    # INT signals that a date was interpreted from its original wording.
    # The full wording is saved in a separate NOTE when it is too long.
    if not converted.startswith("ABT "):
        interpreted = "INT {} ({})".format(converted, text)
        if len(interpreted) <= 35:
            return interpreted, None

    return converted, original


def _formal_interpretation(original, formal):
    """Use GEDCOM X formal data for ambiguous numeric dates."""
    if not formal:
        return None

    formal_match = re.fullmatch(
        r"\+(\d{4})-(\d{2})-(\d{2})", formal
    )
    original_match = re.fullmatch(
        r"(\d{1,2})/(\d{1,2})/(\d{3,4})", original
    )

    if not (formal_match and original_match):
        return None

    year, month, day = map(int, formal_match.groups())
    first, second, original_year = map(
        int, original_match.groups()
    )

    if year != original_year:
        return None

    if (month, day) not in (
        (first, second),
        (second, first),
    ):
        return None

    converted = _calendar_date(year, month, day)

    if converted is None:
        return None

    result = "INT {} ({})".format(converted, original)
    return result if len(result) <= 35 else None


def _fallback(original, text):
    """Keep an unrecognized date without inventing a value."""
    if text.startswith("(") and text.endswith(")"):
        if len(text) <= 35:
            return text, None

    if len(text) <= 33:
        return "({})".format(text), None

    return None, original


def normalize_gedcom_date(original, formal=None):
    """Return (GEDCOM date, unconverted original text)."""
    original = original or ""
    text = " ".join(original.split())

    if not text:
        if formal:
            converted = _formal_simple_date(formal)
            return (converted, None) if converted else (None, formal)

        return None, None

    ranges = (
        (r"(?:BET|BETWEEN)\s+(.+?)\s+AND\s+(.+)", "BET", "AND"),
        (r"ENTRE\s+(.+?)\s+Y\s+(.+)", "BET", "AND"),
        (r"FROM\s+(.+?)\s+TO\s+(.+)", "FROM", "TO"),
        (r"DESDE\s+(.+?)\s+HASTA\s+(.+)", "FROM", "TO"),
    )

    for pattern, prefix, separator in ranges:
        match = re.fullmatch(
            pattern, text, re.IGNORECASE
        )
        if match:
            first = _simple_date(match.group(1))
            second = _simple_date(match.group(2))

            if first and second:
                result = "{} {} {} {}".format(
                    prefix, first, separator, second
                )
                if len(result) <= 35:
                    return result, None

            return _fallback(original, text)

    match = re.fullmatch(
        r"(ABT|ABOUT|CIRCA|CA\.?|HACIA|"
        r"APROX\.?|APROXIMADAMENTE|CAL|EST|"
        r"BEF|BEFORE|ANTES DE|"
        r"AFT|AFTER|DESPU[EÉ]S DE|"
        r"FROM|TO)\s+(.+)",
        text,
        re.IGNORECASE,
    )

    if match:
        prefixes = {
            "ABOUT": "ABT",
            "CIRCA": "ABT",
            "CA": "ABT",
            "HACIA": "ABT",
            "APROX": "ABT",
            "APROXIMADAMENTE": "ABT",
            "BEFORE": "BEF",
            "ANTES DE": "BEF",
            "AFTER": "AFT",
            "DESPUES DE": "AFT",
        }

        prefix = _key(match.group(1))
        prefix = prefixes.get(prefix, prefix)
        converted = _simple_date(match.group(2))

        if converted:
            result = "{} {}".format(prefix, converted)
            if len(result) <= 35:
                return result, None

        return _fallback(original, text)

    converted = _simple_date(text)
    if converted:
        return converted, None

    interpreted = _formal_interpretation(text, formal)
    if interpreted:
        return interpreted, None

    return _formal_fallback(original, text, formal)
