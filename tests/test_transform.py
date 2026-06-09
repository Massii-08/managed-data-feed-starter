"""Tests for feedsmith.transform: normalize_value and transform."""
from __future__ import annotations

import pytest

from feedsmith.models import FieldPolicy, PolicyViolation, Record
from feedsmith.transform import normalize_value, transform


def test_normalize_value_strips_and_collapses_whitespace() -> None:
    assert normalize_value("  hello   world  ") == "hello world"
    assert normalize_value("a\t\tb\nc") == "a b c"
    assert normalize_value("clean") == "clean"


def test_normalize_value_leaves_non_strings_unchanged() -> None:
    assert normalize_value(42) == 42
    assert normalize_value(3.5) == 3.5
    assert normalize_value(None) is None
    obj = {"k": "v"}
    assert normalize_value(obj) is obj


def test_transform_wraps_records_with_source_and_now_iso() -> None:
    policy = FieldPolicy(allowed=["title", "price"])
    raw = [
        {"title": "  Book   One ", "price": "10.00", "drop": "x"},
        {"title": "Book Two", "price": " 20.00 "},
    ]
    now_iso = "2026-01-01T00:00:00+00:00"
    records = transform(raw, policy, source="books.toscrape.com", now_iso=now_iso)

    assert len(records) == 2
    assert all(isinstance(r, Record) for r in records)

    assert records[0].source == "books.toscrape.com"
    assert records[0].fetched_at == now_iso
    assert records[0].fields == {"title": "Book One", "price": "10.00"}

    assert records[1].fields == {"title": "Book Two", "price": "20.00"}


def test_transform_empty_input_returns_empty_list() -> None:
    policy = FieldPolicy(allowed=["title"])
    assert transform([], policy, source="src", now_iso="2026-01-01T00:00:00+00:00") == []


def test_transform_propagates_policy_violation_on_pii() -> None:
    policy = FieldPolicy(allowed=["title", "email"])
    raw = [{"title": "Book", "email": "x@example.com"}]
    with pytest.raises(PolicyViolation):
        transform(raw, policy, source="src", now_iso="2026-01-01T00:00:00+00:00")


def test_transform_normalizes_non_string_values_untouched() -> None:
    policy = FieldPolicy(allowed=["title", "count"])
    raw = [{"title": "  Spaced  Title ", "count": 7}]
    records = transform(raw, policy, source="src", now_iso="t")
    assert records[0].fields == {"title": "Spaced Title", "count": 7}
