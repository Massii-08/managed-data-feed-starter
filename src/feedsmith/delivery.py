"""Delivery sinks for clean, non-PII records (CSV, JSON, webhook).

These sinks take validated :class:`~feedsmith.models.Record` objects and
persist or transmit them. The webhook poster is injectable so tests run
fully offline with no network calls.
"""
from __future__ import annotations

import csv
import json
import os
from typing import Any, Callable, Dict, List, Optional

import typing

from feedsmith.models import Record


class Sink(typing.Protocol):
    """Protocol for a delivery target that consumes records."""

    def deliver(self, records: List[Record]) -> str:
        ...


def _record_row(record: Record) -> Dict[str, Any]:
    """Build the flat JSON/CSV row shape for a single record.

    The row is the record's fields plus the ``source`` and ``fetched_at``
    metadata columns.
    """
    row: Dict[str, Any] = {}
    row.update(record.fields)
    row["source"] = record.source
    row["fetched_at"] = record.fetched_at
    return row


def _ensure_parent_dir(path: str) -> None:
    """Create the parent directory of ``path`` if it does not exist."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


class CsvSink:
    """Write records to a CSV file with a stable, sorted header."""

    def __init__(self, path: str) -> None:
        """Store the destination ``path`` for the CSV output."""
        self.path = path

    def deliver(self, records: List[Record]) -> str:
        """Write ``records`` to the CSV file and return the path.

        The header is the sorted union of all field keys followed by the
        ``source`` and ``fetched_at`` metadata columns.
        """
        _ensure_parent_dir(self.path)
        field_keys: set = set()
        for record in records:
            field_keys.update(record.fields.keys())
        header: List[str] = sorted(field_keys) + ["source", "fetched_at"]
        with open(self.path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            for record in records:
                writer.writerow(_record_row(record))
        return self.path


class JsonSink:
    """Write records to a JSON array file."""

    def __init__(self, path: str) -> None:
        """Store the destination ``path`` for the JSON output."""
        self.path = path

    def deliver(self, records: List[Record]) -> str:
        """Write ``records`` as a JSON array and return the path."""
        _ensure_parent_dir(self.path)
        payload: List[Dict[str, Any]] = [_record_row(r) for r in records]
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return self.path


class WebhookSink:
    """POST records as a JSON payload to a webhook URL.

    The ``poster`` is injectable for offline testing; by default it uses
    ``httpx.post`` lazily so importing this module never requires httpx.
    """

    def __init__(
        self,
        url: str,
        poster: Optional[Callable[[str, list], Any]] = None,
    ) -> None:
        """Store the ``url`` and optional ``poster`` callable."""
        self.url = url
        self.poster = poster

    def _default_poster(self, url: str, payload: list) -> Any:
        """Post the payload using httpx (imported lazily)."""
        import httpx

        return httpx.post(url, json=payload)

    def deliver(self, records: List[Record]) -> str:
        """Build the payload, call the poster, and return the URL."""
        payload: List[Dict[str, Any]] = [_record_row(r) for r in records]
        poster = self.poster if self.poster is not None else self._default_poster
        poster(self.url, payload)
        return self.url
