# Delivery & AI agents — why files, a CLI, and a thin API (not an MCP server)

**TL;DR — A managed data feed should be delivered as clean files (CSV / JSON /
Parquet), a thin documented REST API, and a small CLI. That is the surface both
humans and AI agents consume natively, cheaply, and reliably. A heavyweight MCP
server is *not* the default; it is an optional thin wrapper added on request.**

---

## The pull of the moment

"Expose your data as an [MCP](https://modelcontextprotocol.io) server" is a
popular pitch right now, because AI agents are everywhere and MCP is how an
agent discovers and calls tools. The instinct is: *make the feed an MCP server
so agents can query it.*

For a **data feed**, that instinct is mostly wrong — and following it costs you
money and reliability for little gain.

## Why files + CLI + a thin API win for agents

An agent that loads a naive MCP server pays for every tool definition in its
context window on **every** call — often ~15k tokens before it has done any
work. As the number of tools and the task difficulty grow, both cost and error
rate climb.

By contrast:

- **Flat files (CSV / JSON / Parquet)** are universal. Every language, every
  data warehouse, pandas/polars, and every agent runtime reads them with zero
  custom integration. Parquet in particular is typed and columnar — cheap to
  load and analyze at scale.
- **A thin REST API** (`GET /feeds`, `GET /feeds/{id}/status`,
  `POST /feeds/{id}/run`) is self-describing and callable from anything, by a
  human with `curl` or by an agent writing two lines of code.
- **A small CLI** (`feedsmith pull …`) is the cheapest possible agent surface:
  modern LLMs are heavily pre-trained on shell usage, so calling a command is
  "native" to them. No tool definitions to load, deterministic output, trivial
  to script. The industry calls this **code / CLI execution**, and it routinely
  uses *dramatically* fewer tokens than tool-by-tool MCP calls for the same job.

This is not anti-MCP dogma — it is matching the interface to the job. For a
feed, the job is "give me the data, reliably and cheaply." Files, a CLI, and a
thin API do exactly that.

## Where MCP actually fits

MCP earns its place when a client specifically needs an agent to **discover and
orchestrate** your feed inside an MCP-native host (Claude Desktop, an internal
agent platform), and wants the governance MCP adds: OAuth, audit trails,
multi-tenant access.

When that is a real requirement, the right move is a **thin wrapper around the
existing API**, ideally using the *code-execution* pattern
([Anthropic, Nov 2025](https://www.anthropic.com/engineering/code-execution-with-mcp))
so the agent writes code that calls the feed instead of paying for fat tool
definitions on every turn. That wrapper is small precisely because the real
work already lives behind clean files and a documented API.

So MCP is a **delivery option on request**, not the headline. We never make the
feed depend on it.

## What this means if you are a client

You get data that is **immediately usable** in whatever you already run — a
spreadsheet, a database load, a dashboard, a Python notebook, or an AI agent —
with **no lock-in** to a protocol or a vendor. If, later, you want your AI stack
to call the feed directly, we add a thin MCP layer on top of the same API. You
never pay for plumbing you do not need.

---

### References

- Anthropic — *Code execution with MCP: building more efficient agents* (Nov 2025):
  <https://www.anthropic.com/engineering/code-execution-with-mcp>
- Model Context Protocol: <https://modelcontextprotocol.io>
