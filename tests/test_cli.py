"""Offline tests for the Feedsmith CLI (no network calls).

The ``pull`` command's runner construction is injected with a fake builder so
no HTTP fetch ever happens; the rest of the surface (output override, validate,
version) is pure and tested directly.
"""
from __future__ import annotations

import json
import os

import pytest

from feedsmith.cli import _override_output, main
from feedsmith.config import FeedConfig, load_feed_config
from feedsmith.runner import RunResult

_CSV_OUTPUT = "output:\n  kind: csv\n  path: data/t.csv\n"


def _write_config(tmp_path, output_block: str = _CSV_OUTPUT) -> str:
    """Write a minimal valid feed YAML and return its path."""
    text = (
        "id: t\n"
        "source: books.toscrape.com\n"
        "fields: [title, price]\n"
        "schedule:\n"
        "  interval_seconds: 3600\n"
    ) + output_block
    path = os.path.join(str(tmp_path), "feed.yaml")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _load_config(tmp_path) -> FeedConfig:
    """Load a default (csv-output) FeedConfig from a temp file."""
    return load_feed_config(_write_config(tmp_path))


# --- _override_output ------------------------------------------------------


def test_override_output_no_flags_returns_same_object(tmp_path) -> None:
    """With neither flag set, the config is returned unchanged."""
    config = _load_config(tmp_path)
    assert _override_output(config, None, None) is config


def test_override_output_infers_format_from_extension(tmp_path) -> None:
    """An --out path with a known extension infers the format."""
    config = _load_config(tmp_path)
    new = _override_output(config, None, "out/data.parquet")
    assert new.output.kind == "parquet"
    assert new.output.path == "out/data.parquet"
    # The original config is not mutated.
    assert config.output.kind == "csv"


def test_override_output_explicit_format_wins(tmp_path) -> None:
    """An explicit --format overrides regardless of the path extension."""
    config = _load_config(tmp_path)
    new = _override_output(config, "json", "x.dat")
    assert new.output.kind == "json"
    assert new.output.path == "x.dat"


def test_override_output_format_without_out_raises(tmp_path) -> None:
    """--format without --out is a usage error."""
    config = _load_config(tmp_path)
    with pytest.raises(ValueError):
        _override_output(config, "csv", None)


def test_override_output_unknown_extension_raises(tmp_path) -> None:
    """An --out path with an unknown extension and no --format raises."""
    config = _load_config(tmp_path)
    with pytest.raises(ValueError):
        _override_output(config, None, "out.txt")


# --- pull -------------------------------------------------------------------


class _FakeRunner:
    """Runner stub returning a fixed result, recording that it ran."""

    def __init__(self, result: RunResult) -> None:
        self.result = result
        self.ran = False

    def run_once(self) -> RunResult:
        self.ran = True
        return self.result


def test_pull_runs_feed_prints_result_and_returns_zero(tmp_path, capsys) -> None:
    """`pull` builds a runner, runs it, prints the JSON result, exits 0."""
    config_path = _write_config(tmp_path)
    seen = {}

    def fake_builder(config):
        seen["config"] = config
        return _FakeRunner(
            RunResult(feed_id="t", ok=True, record_count=3, output="o.parquet", error=None)
        ), None

    code = main(
        ["pull", config_path, "--format", "parquet", "--out", "o.parquet"],
        runner_builder=fake_builder,
    )

    assert code == 0
    # The CLI override reached the runner builder.
    assert seen["config"].output.kind == "parquet"
    assert seen["config"].output.path == "o.parquet"
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["record_count"] == 3


def test_pull_failure_returns_one(tmp_path, capsys) -> None:
    """A failed run returns exit code 1 and prints the captured error."""
    config_path = _write_config(tmp_path)

    def fake_builder(config):
        return _FakeRunner(
            RunResult(feed_id="t", ok=False, record_count=0, output=None, error="boom")
        ), None

    code = main(["pull", config_path], runner_builder=fake_builder)

    assert code == 1
    assert "boom" in capsys.readouterr().out


def test_pull_format_without_out_is_usage_error(tmp_path) -> None:
    """`pull --format` without `--out` exits 2 (argparse usage error)."""
    config_path = _write_config(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["pull", config_path, "--format", "parquet"], runner_builder=lambda c: (None, None))
    assert exc.value.code == 2


# --- validate / version / no-command --------------------------------------


def test_validate_ok_returns_zero(tmp_path, capsys) -> None:
    """`validate` on a good config returns 0 and prints an OK line."""
    config_path = _write_config(tmp_path)
    assert main(["validate", config_path]) == 0
    assert "OK" in capsys.readouterr().out


def test_validate_invalid_returns_two(tmp_path, capsys) -> None:
    """`validate` on a config missing required fields returns 2."""
    bad = os.path.join(str(tmp_path), "bad.yaml")
    with open(bad, "w", encoding="utf-8") as handle:
        handle.write("id: x\n")  # missing source/fields/schedule/output
    assert main(["validate", bad]) == 2
    assert "INVALID" in capsys.readouterr().out


def test_version_returns_zero(capsys) -> None:
    """`version` prints the package version and returns 0."""
    assert main(["version"]) == 0
    assert "feedsmith" in capsys.readouterr().out


def test_no_command_prints_help_and_returns_one(capsys) -> None:
    """Invoking with no subcommand prints help and returns 1."""
    assert main([]) == 1
