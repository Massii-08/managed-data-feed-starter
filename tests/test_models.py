"""Tests for feedsmith.models: FieldPolicy, Record, utcnow_iso."""
from __future__ import annotations

import dataclasses

import pytest

from feedsmith.models import (
    PII_FIELDS,
    FieldPolicy,
    PolicyViolation,
    Record,
    utcnow_iso,
)


def test_utcnow_iso_returns_utc_offset_string() -> None:
    value = utcnow_iso()
    assert isinstance(value, str)
    assert value.endswith("+00:00")
    # Parseable back to an aware datetime.
    from datetime import datetime

    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0.0


def test_record_is_frozen() -> None:
    rec = Record(source="src", fields={"title": "Book"}, fetched_at="2026-01-01T00:00:00+00:00")
    assert rec.source == "src"
    assert rec.fields == {"title": "Book"}
    assert rec.fetched_at == "2026-01-01T00:00:00+00:00"
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.source = "other"  # type: ignore[misc]


def test_policy_keeps_only_allowed_keys_and_drops_others() -> None:
    policy = FieldPolicy(allowed=["title", "price"])
    raw = {"title": "Book", "price": "10.00", "extra": "drop me", "noise": 42}
    result = policy.validate(raw)
    assert result == {"title": "Book", "price": "10.00"}
    # A NEW dict is returned, not the same object.
    assert result is not raw


def test_policy_returns_only_present_allowed_keys() -> None:
    policy = FieldPolicy(allowed=["title", "price", "stock"])
    raw = {"title": "Book"}
    result = policy.validate(raw)
    assert result == {"title": "Book"}


def test_policy_raises_on_pii_field() -> None:
    policy = FieldPolicy(allowed=["email"])
    with pytest.raises(PolicyViolation):
        policy.validate({"email": "x@example.com"})


def test_policy_pii_check_is_case_insensitive() -> None:
    policy = FieldPolicy(allowed=["title"])
    with pytest.raises(PolicyViolation):
        policy.validate({"title": "Book", "Email": "x@example.com"})
    with pytest.raises(PolicyViolation):
        policy.validate({"PHONE": "12345"})


def test_policy_rejects_each_known_pii_field() -> None:
    for pii in PII_FIELDS:
        policy = FieldPolicy(allowed=[pii])
        with pytest.raises(PolicyViolation):
            policy.validate({pii: "value"})


def test_policy_allows_clean_record_when_no_pii_present() -> None:
    policy = FieldPolicy(allowed=["title", "rating"])
    result = policy.validate({"title": "Book", "rating": "Three", "junk": "x"})
    assert result == {"title": "Book", "rating": "Three"}
