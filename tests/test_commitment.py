"""The commitment parser: raw text -> (commitment_cents, currency). Pure function."""
import csv
from pathlib import Path

import pytest

from app.commitment import format_commitment, parse_commitment

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "funds.csv"


@pytest.mark.parametrize(
    "text, expected",
    [
        # One case per shape found in data/funds.csv.
        ("$15,000,000 USD", (1_500_000_000, "USD")),
        ("$10,000,000.25 USD", (1_000_000_025, "USD")),
        ("£12,500,000 GBP", (1_250_000_000, "GBP")),
        ("€40,000,000 EUR", (4_000_000_000, "EUR")),
        # Cents are hundredths of the major unit for every currency, JPY included.
        ("¥1,125,000,000 JPY", (112_500_000_000, "JPY")),
        ("USD 10,000,000", (1_000_000_000, "USD")),
        ("$500,000", (50_000_000, "USD")),  # bare $ is assumed to be USD
        ("1250000 USD", (125_000_000, "USD")),
        ("~$1,000,000 USD", (100_000_000, "USD")),  # approximate flag dropped
        ("$3,000,000 usd", (300_000_000, "USD")),
        ("  $1,250,000 USD  ", (125_000_000, "USD")),
        # Missing values.
        ("", (None, None)),
        ("Not reported", (None, None)),
        ("Undisclosed", (None, None)),
        ("TBD", (None, None)),
        # Variations of the above that the rules also cover.
        (None, (None, None)),
        ("  not REPORTED ", (None, None)),
        ("$1.5 USD", (150, "USD")),
        ("gbp 2,000", (200_000, "GBP")),
        ("£2,000", (200_000, "GBP")),
    ],
)
def test_parses_commitment(text, expected):
    assert parse_commitment(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "lots",
        "USD",
        "$",
        "1,000,000",  # no symbol or code: currency unknown
        "£1,000 USD",  # symbol contradicts code
        "$1,000 USD EUR",
        "$1,000.123 USD",  # sub-cent precision
        "$1,00,0 USD",  # misplaced thousands separators
        "-$1,000 USD",
    ],
)
def test_rejects_unparseable_commitment(text):
    with pytest.raises(ValueError):
        parse_commitment(text)


def test_parses_every_commitment_in_the_csv():
    with CSV_PATH.open(newline="") as f:
        results = [parse_commitment(row["commitment"]) for row in csv.DictReader(f)]

    assert len(results) == 500
    assert sum(1 for cents, _ in results if cents is None) == 25
    assert all((cents is None) == (currency is None) for cents, currency in results)


@pytest.mark.parametrize(
    "cents, currency, expected",
    [
        (1_500_000_000, "USD", "USD 15,000,000"),
        (1_000_000_025, "USD", "USD 10,000,000.25"),
        (150, "GBP", "GBP 1.50"),
        (5, "JPY", "JPY 0.05"),
        (0, "EUR", "EUR 0"),
        (None, None, ""),
    ],
)
def test_formats_commitment(cents, currency, expected):
    assert format_commitment(cents, currency) == expected


def test_formatting_round_trips_every_commitment_in_the_csv():
    with CSV_PATH.open(newline="") as f:
        parsed = [parse_commitment(row["commitment"]) for row in csv.DictReader(f)]

    assert all(parse_commitment(format_commitment(*value)) == value for value in parsed)
