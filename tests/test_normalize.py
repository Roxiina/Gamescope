"""Tests des règles d'homogénéisation, sur des valeurs réelles rencontrées dans les sources."""
from datetime import date

import pytest

from cleaning import normalize as n


@pytest.mark.parametrize("raw, expected", [
    ("Far Cry® New Dawn", "Far Cry New Dawn"),
    ("Call of Duty®: Infinite Warfare", "Call of Duty: Infinite Warfare"),
    ("OCTOPATH TRAVELER™ ", "OCTOPATH TRAVELER"),
    ("  ", None),
    (None, None),
])
def test_clean_name(raw, expected):
    assert n.clean_name(raw) == expected


def test_name_key_matches_variants_across_sources():
    assert n.name_key("LEGO® Star Wars™ - The Complete Saga") == n.name_key("LEGO Star Wars: The Complete Saga")
    assert n.name_key("Pokémon") == "pokemon"
    assert n.name_key("Ratchet & Clank") == "ratchet and clank"


@pytest.mark.parametrize("raw, expected", [
    ("29 Sep, 2015", date(2015, 9, 29)),
    ("Aug 1, 2023", date(2023, 8, 1)),
    ("Sep 2015", date(2015, 9, 1)),
    ("2015-09-29", date(2015, 9, 29)),
    ("", None),
    ("Coming soon", None),
    (None, None),
])
def test_parse_date(raw, expected):
    assert n.parse_date(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("12,99€", 12.99),
    ("9,--€", 9.0),
    ("1.299,00€", 1299.0),
    ("Free To Play", 0.0),
    ("Free", 0.0),
    ("Play for Free!", 0.0),
    ("7,99€ / month", None),
    ("Shadow of the Tomb Raider Free Trial", None),
    ("Install Now", None),
])
def test_parse_price_text(raw, expected):
    assert n.parse_price_text(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("1,000,000 .. 2,000,000", (1_000_000, 2_000_000)),
    ("20000 - 50000", (20_000, 50_000)),
    ("n/a", (None, None)),
])
def test_parse_owners(raw, expected):
    assert n.parse_owners(raw) == expected


def test_year_or_none():
    assert n.year_or_none("2006") == 2006
    assert n.year_or_none("N/A") is None
    assert n.year_or_none("2035") is None


def test_units_and_codes():
    assert n.millions_to_units(41.49) == 41_490_000
    assert n.language_code("schinese") == "zh-Hans"
    assert n.language_code("klingon") is None
    assert n.platform_name("X360") == "Xbox 360"
    assert n.bounded(0, 1, 100) is None
    assert n.bounded(88, 1, 100) == 88


def test_apostrophes_and_compact_key():
    assert n.name_key("Assassin’s Creed III") == n.name_key("Assassin's Creed III")
    assert n.compact_key(n.name_key("Puyo PuyoTetris")) == n.compact_key(n.name_key("Puyo Puyo Tetris"))


@pytest.mark.parametrize("a, b, same", [
    ("final fantasy x", "final fantasy ix", False),
    ("dark souls ii", "dark souls iii", False),
    ("call of duty 2", "call of duty 3", False),
    ("street fighter iv", "street fighter v", False),
    ("dawn of war ii", "dawn of war ii", True),
    ("civilization", "civilization", True),
])
def test_sequel_markers(a, b, same):
    assert (n.sequel_markers(a) == n.sequel_markers(b)) is same
