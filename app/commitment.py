"""Parse a raw commitment string into (commitment_cents, currency).

Pure function, no dependencies. Rules (see docs/PLAN.md):
- case- and whitespace-insensitive; the ISO code may precede or follow the amount
- a currency symbol alone implies its currency (bare `$` is assumed to be USD)
- a leading `~` (approximate) is accepted and dropped
- '', 'Not reported', 'Undisclosed', 'TBD' (or None) -> (None, None)
- cents are hundredths of the major unit for every currency, JPY included
Anything else raises ValueError.
"""
import re

MISSING = {"", "not reported", "undisclosed", "tbd"}

SYMBOLS = {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY"}

PATTERN = re.compile(
    r"""
    ~?\s*
    (?:(?P<code_before>[a-z]{3})\s+)?
    (?P<symbol>[$£€¥])?\s*
    (?P<units>\d{1,3}(?:,\d{3})+|\d+)
    (?:\.(?P<fraction>\d{1,2}))?
    (?:\s+(?P<code_after>[a-z]{3}))?
    """,
    re.VERBOSE | re.IGNORECASE,
)


def parse_commitment(text):
    if text is None or text.strip().lower() in MISSING:
        return None, None

    match = PATTERN.fullmatch(text.strip())
    if not match or (match["code_before"] and match["code_after"]):
        raise ValueError(f"Unparseable commitment: {text!r}")

    code = (match["code_before"] or match["code_after"] or "").upper() or None
    implied = SYMBOLS.get(match["symbol"])
    if code and implied and code != implied:
        raise ValueError(f"Symbol contradicts currency code: {text!r}")
    currency = code or implied
    if currency is None:
        raise ValueError(f"No currency in commitment: {text!r}")

    units = int(match["units"].replace(",", ""))
    cents = int((match["fraction"] or "0").ljust(2, "0"))
    return units * 100 + cents, currency
