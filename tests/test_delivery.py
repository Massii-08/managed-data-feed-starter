"""Offline tests for delivery sinks (CSV, JSON, Parquet, webhook)."""
from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, List, Tuple

import pytest

from feedsmith.delivery import CsvSink, JsonSink, ParquetSink, WebhookSink
from feedsmith.models import Record


def _sample_records() -> List[Record]:
    """Build a deterministic pair of records for assertions."""
    return [
        Record(
            source="books.toscrape.com",
            fields={"title": "Book A", "price": "£10.00"},
            fetched_at="2026-01-01T00:00:00+00:00",
        ),
        Record(
            source="books.toscrape.com",
            fields={"title": "Book B", "price": "£20.00"},
            fetched_at="2026-01-01T00:00:00+00:00",
        ),
    ]


def test_csv_sink_writes_header_and_rows(tmp_path) -> None:
    """CsvSink writes a readable CSV with source + fetched_at columns."""
    path = os.path.join(str(tmp_path), "nested", "out.csv")
    sink = CsvSink(path)
    returned = sink.deliver(_sample_records())

    assert returned == path
    assert os.path.exists(path)

    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    # Header is sorted field keys + metadata columns.
    assert reader.fieldnames == ["price", "title", "source", "fetched_at"]
    assert len(rows) == 2
    assert rows[0]["title"] == "Book A"
    assert rows[0]["price"] == "£10.00"
    assert rows[0]["source"] == "books.toscrape.com"
    assert rows[0]["fetched_at"] == "2026-01-01T00:00:00+00:00"
    assert rows[1]["title"] == "Book B"


def test_csv_sink_unions_field_keys(tmp_path) -> None:
    """CsvSink header is the sorted union across heterogeneous records."""
    path = os.path.join(str(tmp_path), "union.csv")
    records = [
        Record("s", {"a": "1"}, "2026-01-01T00:00:00+00:00"),
        Record("s", {"b": "2"}, "2026-01-01T00:00:00+00:00"),
    ]
    CsvSink(path).deliver(records)

    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == ["a", "b", "source", "fetched_at"]
        rows = list(reader)

    # Missing keys serialize as empty strings.
    assert rows[0]["a"] == "1"
    assert rows[0]["b"] == ""
    assert rows[1]["a"] == ""
    assert rows[1]["b"] == "2"


def test_json_sink_round_trips(tmp_path) -> None:
    """JsonSink writes a JSON array that round-trips with json.load."""
    path = os.path.join(str(tmp_path), "deep", "out.json")
    sink = JsonSink(path)
    returned = sink.deliver(_sample_records())

    assert returned == path
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)

    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0] == {
        "title": "Book A",
        "price": "£10.00",
        "source": "books.toscrape.com",
        "fetched_at": "2026-01-01T00:00:00+00:00",
    }
    assert data[1]["title"] == "Book B"


def test_webhook_sink_uses_injected_poster_no_network() -> None:
    """WebhookSink calls the injected poster with (url, payload)."""
    captured: List[Tuple[str, list]] = []

    def fake_poster(url: str, payload: list) -> Any:
        captured.append((url, payload))
        return "ok"

    sink = WebhookSink("https://example.test/hook", poster=fake_poster)
    returned = sink.deliver(_sample_records())

    assert returned == "https://example.test/hook"
    assert len(captured) == 1
    url, payload = captured[0]
    assert url == "https://example.test/hook"
    assert isinstance(payload, list)
    assert len(payload) == 2
    first: Dict[str, Any] = payload[0]
    assert first == {
        "title": "Book A",
        "price": "£10.00",
        "source": "books.toscrape.com",
        "fetched_at": "2026-01-01T00:00:00+00:00",
    }


def test_webhook_sink_empty_records() -> None:
    """WebhookSink posts an empty list when there are no records."""
    captured: List[Tuple[str, list]] = []

    def fake_poster(url: str, payload: list) -> Any:
        captured.append((url, payload))
        return None

    WebhookSink("https://example.test/hook", poster=fake_poster).deliver([])
    assert captured == [("https://example.test/hook", [])]


def test_parquet_sink_round_trips(tmp_path) -> None:
    """ParquetSink writes a Parquet file that reads back to the row shape."""
    pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    path = os.path.join(str(tmp_path), "deep", "out.parquet")
    sink = ParquetSink(path)
    returned = sink.deliver(_sample_records())

    assert returned == path
    assert os.path.exists(path)

    table = pq.read_table(path)
    # Schema is sorted field keys + metadata columns (mirrors CsvSink).
    assert table.column_names == ["price", "title", "source", "fetched_at"]
    rows = table.to_pylist()
    assert len(rows) == 2
    assert rows[0] == {
        "price": "£10.00",
        "title": "Book A",
        "source": "books.toscrape.com",
        "fetched_at": "2026-01-01T00:00:00+00:00",
    }
    assert rows[1]["title"] == "Book B"


def test_parquet_sink_unions_field_keys(tmp_path) -> None:
    """ParquetSink schema is the sorted union; missing keys are null."""
    pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    path = os.path.join(str(tmp_path), "union.parquet")
    records = [
        Record("s", {"a": "1"}, "2026-01-01T00:00:00+00:00"),
        Record("s", {"b": "2"}, "2026-01-01T00:00:00+00:00"),
    ]
    ParquetSink(path).deliver(records)

    table = pq.read_table(path)
    assert table.column_names == ["a", "b", "source", "fetched_at"]
    rows = table.to_pylist()
    # Missing keys serialize as null (None), not empty string.
    assert rows[0]["a"] == "1" and rows[0]["b"] is None
    assert rows[1]["a"] is None and rows[1]["b"] == "2"


def test_parquet_sink_empty_records(tmp_path) -> None:
    """ParquetSink writes a valid, empty Parquet file for zero records."""
    pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    path = os.path.join(str(tmp_path), "empty.parquet")
    returned = ParquetSink(path).deliver([])

    assert returned == path
    assert os.path.exists(path)
    assert pq.read_table(path).to_pylist() == []
