"""Cleaning and normalization of raw scraped records into Feedsmith records.

Applies the no-PII :class:`~feedsmith.models.FieldPolicy` and whitespace
normalization to raw dicts from public sources, producing immutable
:class:`~feedsmith.models.Record` objects.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from feedsmith.models import FieldPolicy, Record

# Matches one or more whitespace characters for collapsing internal runs.
_WS_RUN = re.compile(r"\s+")


def normalize_value(v: Any) -> Any:
    """Normalize a single value.

    For strings: strip leading/trailing whitespace and collapse internal
    whitespace runs to a single space. Non-string values are returned
    unchanged.
    """
    if isinstance(v, str):
        return _WS_RUN.sub(" ", v.strip())
    return v


def transform(
    raw_records: List[Dict[str, Any]],
    policy: FieldPolicy,
    source: str,
    now_iso: str,
) -> List[Record]:
    """Validate, normalize, and wrap raw records into :class:`Record` objects.

    Each raw dict is validated against ``policy`` (a
    :class:`~feedsmith.models.PolicyViolation` propagates as a fail-safe and is
    never swallowed), each value is normalized, and the cleaned mapping is
    wrapped in a :class:`Record` tagged with ``source`` and ``now_iso``.

    Returns:
        A list of clean records in the same order as ``raw_records``.
    """
    records: List[Record] = []
    for raw in raw_records:
        clean = policy.validate(raw)
        normalized: Dict[str, Any] = {
            key: normalize_value(value) for key, value in clean.items()
        }
        records.append(Record(source=source, fields=normalized, fetched_at=now_iso))
    return records
