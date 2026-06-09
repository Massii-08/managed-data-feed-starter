# Offer mapping

Feedsmith is the runnable shape of a **Managed Data Feed** service. This page
maps each repository component to the part of the commercial offer it delivers,
so the technical template and the service it encodes line up one-to-one.

The offer reads, plainly: *"I build you a feed that scrapes a public source,
keeps only clean factual / non-PII data, runs it on a schedule, watches it, fixes
it when it breaks, and delivers it where you want it. You operate and own the
data."*

## Component → offer

| Repository component | Modules | Commercial offer it delivers | Indicative price |
|---|---|---|---|
| **Scraper + field policy + config** — define the public source, parse it, lock the field allowlist | `feedsmith.scraper`, `feedsmith.models` (`FieldPolicy`), `feedsmith.transform`, `feedsmith.config`, `feeds/*.yaml` | **Setup** — stand up a new feed against your chosen public source with a no-PII field allowlist | 500–1,000 EUR one-time |
| **Scheduler + sinks** — run on a cadence and deliver clean output | `feedsmith.scheduler`, `feedsmith.runner`, `feedsmith.delivery` (`CsvSink`/`JsonSink`/`WebhookSink`) | **Scheduled delivery** — your feed runs on an interval or cron and lands as CSV, JSON, or a webhook | included in setup; recurring below |
| **Monitor + self-heal** — track health, alert, and recover | `feedsmith.monitor` (`FeedHealth`, `Monitor` alert + heal hook) | **Monitoring — "I fix it when it breaks"** — failures are detected, alerted, and self-healed; you are not the one paging at 2 a.m. | 150–500 EUR / month |
| **Docker + control plane** — a service you run and own | `Dockerfile`, `docker-compose.yml`, `feedsmith.api` (FastAPI: `/health`, `/feeds`, `/feeds/{id}/status`, `/feeds/{id}/run`) | **You operate and own it** — deploy the container on your own infrastructure; the data and the running service are yours | self-hosted by you |

## Why it maps cleanly

- The **field allowlist** that backs the setup deliverable is the same
  `FieldPolicy` that enforces the no-PII guarantee in code — the commercial
  promise and the runtime behavior are one and the same.
- The **monthly monitoring** line is concrete, not vague: `Monitor.observe()`
  fires an alert and an optional heal hook the moment a feed crosses its failure
  threshold, which is exactly the "I fix it when it breaks" value.
- The **you-operate** framing is real because the whole thing ships as a
  container with a thin FastAPI control plane. You run it on your own
  infrastructure; you own the delivered data. Feedsmith works against public
  sources for factual / non-PII data, and is not affiliated with any site it can
  read.
