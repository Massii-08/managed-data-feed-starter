# Feedsmith — Managed Data Feed Starter

[![CI](https://github.com/Massii-08/managed-data-feed-starter/actions/workflows/ci.yml/badge.svg)](https://github.com/Massii-08/managed-data-feed-starter/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

> A runnable FastAPI template that turns a public source into a clean, scheduled,
> self-healing data feed — and delivers it as CSV, JSON, or a webhook payload.

Feedsmith scrapes a **public source** on a schedule, enforces a **no-PII field
policy in code**, monitors feed health with **self-healing**, and ships clean
**factual / non-PII data** wherever you want it. You operate and own the data.

---

## The offer this encodes

Feedsmith is the reference implementation of a **Managed Data Feed**:

1. **Scrape a public source** — pull factual, non-PII data (prices, specs,
   stock, listings) from public, logged-out pages.
2. **Clean it** — a `FieldPolicy` keeps only allowlisted fields and **fails the
   run** if any PII-shaped field appears. Values are normalized (whitespace
   collapsed, trimmed).
3. **Schedule it** — APScheduler runs the feed on an interval or a cron.
4. **Monitor and fix it** — a `Monitor` watches consecutive failures and triggers
   an alert plus an optional self-heal hook when a feed goes down.
5. **Deliver it** — write a CSV/JSON file or POST a webhook payload.

Every stage is plain, typed Python with injectable clocks, sleeps, fetchers, and
sinks, so the whole thing is **fully testable offline**.

---

## Architecture

```
                          FastAPI control plane
        ( /health  ·  /feeds  ·  /feeds/{id}/status  ·  /feeds/{id}/run )
        +-----------------------------------------------------------------+
        |                                                                 |
        |   +-----------+   FeedScheduler (interval / cron)               |
        |   | Scheduler |---------------------------+                     |
        |   +-----------+                            |                     |
        |                                            v                     |
        |   +---------+    +---------+    +---------------+    +---------+  |
        |   | Fetcher |--->| Scraper |--->| Field  Policy |--->| transform| |
        |   | (httpx) |    | (bs4)   |    | (no-PII gate) |    | normalize| |
        |   +---------+    +---------+    +---------------+    +----+----+  |
        |        ^                                                  |       |
        |        | RateLimiter (polite)                            v       |
        |        |                                            +---------+   |
        |   +---------+   observe(health)                     |  Sink   |   |
        |   | Monitor |<-------------------------------------| csv/json |   |
        |   | + heal  |   alert() + heal() on N failures      | webhook |   |
        |   +---------+                                       +---------+   |
        +-----------------------------------------------------------------+
                       FeedRunner.run_once() never raises;
                  records success/failure into FeedHealth each run.
```

- **Fetcher** (`feedsmith.fetcher`) — `HttpxFetcher` with a `RateLimiter`, retries,
  and backoff. Optional `ImpersonateFetcher` (curl_cffi TLS impersonation) for
  hard public sites, behind the `[impersonate]` extra.
- **Scraper** (`feedsmith.scraper`) — `BookstoreScraper` parses the demo target
  with BeautifulSoup into plain factual dicts.
- **Field policy + transform** (`feedsmith.models`, `feedsmith.transform`) — the
  in-code no-PII enforcement and value normalization.
- **Sink** (`feedsmith.delivery`) — `CsvSink`, `JsonSink`, `WebhookSink`.
- **Monitor + runner + scheduler** (`feedsmith.monitor`, `feedsmith.runner`,
  `feedsmith.scheduler`) — health tracking, self-heal, and orchestration.
- **Config + API** (`feedsmith.config`, `feedsmith.api`) — YAML-driven feeds and
  the FastAPI control plane.

---

## Quickstart

```bash
# 1. Create and activate a virtual environment (Python 3.9+).
python -m venv .venv
source .venv/bin/activate

# 2. Install Feedsmith (editable) with dev extras.
pip install -e '.[dev]'

# 3. Run the test suite — fully offline, no network calls.
pytest

# 4. Launch the FastAPI control plane.
uvicorn feedsmith.api:app --host 0.0.0.0 --port 8000
```

With the server running, exercise the four endpoints:

```bash
# Liveness probe.
curl http://localhost:8000/health
# -> {"status":"ok","service":"feedsmith"}

# List configured feeds and their current status.
curl http://localhost:8000/feeds

# Inspect one feed's health snapshot.
curl http://localhost:8000/feeds/books-demo/status

# Trigger a single run on demand (this one hits the public sandbox).
curl -X POST http://localhost:8000/feeds/books-demo/run
```

### The demo feed

The bundled `feeds/books_demo.yaml` feed targets
[`books.toscrape.com`](https://books.toscrape.com), a **sanctioned scraping
sandbox** published specifically for practice. Its e-commerce price/stock data is
**factual and contains zero PII** by construction. A live demo run (`POST
/feeds/books-demo/run`, or `scripts/live_smoke.py`) reaches out to that public
sandbox; **every test, by contrast, runs fully offline** with canned HTML.

---

## Legal & scope

Feedsmith is built to operate inside a clear, defensible zone:

- **Public sources only** — public, logged-out pages.
- **Factual / non-PII data only** — prices, specs, stock, listings. The no-PII
  rule is **enforced in code** by `FieldPolicy`: any PII-shaped field aborts the
  run, so personal data never reaches a sink.
- **Respect robots.txt and polite rate limits** — the `RateLimiter` spaces
  requests; you stay within what a site allows.
- **You operate and own the data** — you run this, you own the output. Feedsmith
  is **not affiliated with any site** it can read.

Full doctrine: [docs/legal-safe.md](docs/legal-safe.md). Commercial framing:
[docs/offer-mapping.md](docs/offer-mapping.md).

---

## License

MIT — see [LICENSE](LICENSE).
