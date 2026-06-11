"""Command-line interface for Feedsmith.

Exposes the managed data feed as a thin, agent-friendly CLI::

    feedsmith pull <feed.yaml> [--format csv|json|parquet] [--out PATH]
    feedsmith validate <feed.yaml>
    feedsmith version

A CLI — together with clean files and the REST API — is the surface that both
humans and LLM-based agents consume natively and cheaply (no per-call tool
definitions to load). See ``docs/delivery-and-ai-agents.md`` for the rationale.

The run path is injectable (``runner_builder``) so tests execute fully offline
with no network call.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
from typing import Callable, List, Optional, Tuple

from feedsmith import __version__
from feedsmith.config import FeedConfig, OutputConfig, load_feed_config
from feedsmith.monitor import FeedHealth
from feedsmith.runner import FeedRunner, build_runner

# Factory signature used by ``pull``: a config -> (runner, health) builder.
RunnerBuilder = Callable[[FeedConfig], Tuple[FeedRunner, FeedHealth]]

# File output formats the CLI can target via --format / --out.
_FILE_FORMATS = ("csv", "json", "parquet")
_EXT_TO_FORMAT = {".csv": "csv", ".json": "json", ".parquet": "parquet"}


def _override_output(
    config: FeedConfig,
    fmt: Optional[str],
    out: Optional[str],
) -> FeedConfig:
    """Return ``config`` with its output overridden by CLI flags.

    Resolution rules:
      * Neither flag set -> ``config`` is returned unchanged (same object).
      * ``out`` set, ``fmt`` unset -> format is inferred from the extension.
      * ``fmt`` set -> that file format is used; ``out`` is then required.

    Raises:
        ValueError: if the format cannot be inferred, or ``--format`` is given
            without ``--out``.
    """
    if fmt is None and out is None:
        return config
    if fmt is None:
        ext = os.path.splitext(out or "")[1].lower()
        fmt = _EXT_TO_FORMAT.get(ext)
        if fmt is None:
            raise ValueError(
                "cannot infer output format from %r; "
                "pass --format csv|json|parquet" % (out,)
            )
    if out is None:
        raise ValueError("--format %s requires --out PATH" % (fmt,))
    new_output = OutputConfig(kind=fmt, path=out)
    return config.model_copy(update={"output": new_output})


def cmd_pull(args: argparse.Namespace, runner_builder: RunnerBuilder) -> int:
    """Run a feed once and print its JSON result.

    Returns 0 when the run succeeded, 1 when it failed (the failure is captured
    in the printed result, never raised — mirroring the runner's fail-safe).
    """
    config = load_feed_config(args.config)
    config = _override_output(config, args.format, args.out)
    runner, _health = runner_builder(config)
    result = runner.run_once()
    print(json.dumps(dataclasses.asdict(result), indent=2))
    return 0 if result.ok else 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a feed config file. Returns 0 if valid, 2 if invalid."""
    try:
        config = load_feed_config(args.config)
    except Exception as exc:  # surface the validation error as a clean line
        print("INVALID: %s" % (exc,))
        return 2
    print(
        "OK: feed '%s' -> source '%s', output '%s'"
        % (config.id, config.source, config.output.kind)
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the ``feedsmith`` CLI."""
    parser = argparse.ArgumentParser(
        prog="feedsmith",
        description=(
            "Managed Data Feed — pull clean, factual, non-PII data "
            "from a public source."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version="feedsmith %s" % (__version__,),
    )
    sub = parser.add_subparsers(dest="command")

    p_pull = sub.add_parser("pull", help="run a feed once and deliver its records")
    p_pull.add_argument("config", help="path to a feed YAML config")
    p_pull.add_argument(
        "--format",
        choices=_FILE_FORMATS,
        default=None,
        help="override the output format (csv, json, parquet)",
    )
    p_pull.add_argument(
        "--out",
        default=None,
        help="override the output file path",
    )

    p_validate = sub.add_parser("validate", help="validate a feed YAML config")
    p_validate.add_argument("config", help="path to a feed YAML config")

    sub.add_parser("version", help="print the Feedsmith version")
    return parser


def main(
    argv: Optional[List[str]] = None,
    runner_builder: RunnerBuilder = build_runner,
) -> int:
    """Entry point for the ``feedsmith`` console script.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).
        runner_builder: Factory used by ``pull`` to build a runner from config;
            injectable so tests run without any network call.

    Returns:
        A process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "pull":
        try:
            return cmd_pull(args, runner_builder)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))  # prints usage to stderr and exits with 2
    if args.command == "validate":
        return cmd_validate(args)
    if args.command == "version":
        print("feedsmith %s" % (__version__,))
        return 0

    parser.print_help()
    return 1
