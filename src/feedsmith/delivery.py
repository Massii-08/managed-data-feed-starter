"""Delivery sinks for clean, non-PII records (CSV, JSON, Parquet, webhook).

These sinks take validated :class:`~feedsmith.models.Record` objects and
persist or transmit them. The webhook poster is injectable so tests run
fully offline with no network calls, and ``pyarrow`` (Parquet) is imported
lazily so importing this module never requires the optional dependency.
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


def _sorted_field_columns(records: List[Record]) -> List[str]:
    """Return the sorted union of all field keys across ``records``.

    This is the stable column order shared by the file sinks (CSV/Parquet)
    so heterogeneous records always serialize to the same schema, with any
    missing key rendered as an empty value / null.
    """
    keys: set = set()
    for record in records:
        keys.update(record.fields.keys())
    return sorted(keys)


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
        header: List[str] = _sorted_field_columns(records) + ["source", "fetched_at"]
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


def _load_pyarrow():
    """Import pyarrow lazily, with a clear message if the extra is missing.

    Returns the ``pyarrow`` and ``pyarrow.parquet`` modules. Raises a
    :class:`RuntimeError` (not :class:`ImportError`) so the failure reads as a
    setup instruction rather than a stack-trace internal.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "ParquetSink requires the optional 'pyarrow' dependency. "
            "Install it with: pip install 'feedsmith[parquet]'"
        ) from exc
    return pa, pq


class ParquetSink:
    """Write records to a columnar Apache Parquet file.

    Parquet is the efficient, typed, columnar format that data warehouses,
    pandas/polars, and AI/data pipelines load natively and cheaply — making a
    delivered feed trivial to consume downstream. Requires the optional
    ``pyarrow`` dependency (``pip install 'feedsmith[parquet]'``), imported
    lazily so the rest of the package never depends on it.
    """

    def __init__(self, path: str) -> None:
        """Store the destination ``path`` for the Parquet output."""
        self.path = path

    def deliver(self, records: List[Record]) -> str:
        """Write ``records`` to a Parquet file and return the path.

        The schema is the sorted union of all field keys followed by the
        ``source`` and ``fetched_at`` metadata columns; keys missing from a
        given record are written as nulls. An empty record list still writes a
        valid (empty) Parquet file.
        """
        pa, pq = _load_pyarrow()
        _ensure_parent_dir(self.path)
        columns: List[str] = _sorted_field_columns(records) + ["source", "fetched_at"]
        rows: List[Dict[str, Any]] = [_record_row(r) for r in records]
        data: Dict[str, list] = {col: [row.get(col) for row in rows] for col in columns}
        pq.write_table(pa.table(data), self.path)
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
