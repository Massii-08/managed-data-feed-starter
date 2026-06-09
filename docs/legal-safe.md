# Legal-safe doctrine

Feedsmith is designed to stay inside a clear, defensible operating zone. This
document spells out that zone and shows how the code itself enforces the parts
that matter most.

## The zone

1. **Public, logged-out pages only.**
   Feedsmith reads pages that any visitor can see without an account, without
   logging in, and without circumventing a paywall. It works with public
   sources — nothing gated, nothing private.

2. **Factual / non-PII data only.**
   The data of interest is factual: prices, specs, stock levels, public
   listings. These are objective facts about products and offerings, not
   information about people. Feedsmith does **not** collect personal data.

3. **Respect robots.txt and polite rate limits.**
   Feedsmith honors the access expectations a site publishes and spaces its
   requests so it behaves like a considerate visitor. The built-in
   `RateLimiter` guarantees a minimum interval between successive requests, so a
   feed stays gentle on the source.

4. **Builder, not operator.**
   This repository is a **starter template**. The author builds and ships the
   tooling; the person who runs a feed operates it and owns its output. You
   operate and own the data. Feedsmith is not affiliated with any site it can
   read, and ships with a single demo target that is a sanctioned scraping
   sandbox.

## The PII guard is enforced in code

The no-PII rule is not just a promise in prose — it is a runtime gate.

`FieldPolicy` (in `feedsmith.models`) is constructed with an **allowlist** of
the exact fields a feed may keep. On every record it calls `validate(raw)`:

- If **any** key matches a known PII-shaped field (compared
  case-insensitively against `PII_FIELDS` — names, emails, phones, addresses,
  identifiers, avatars, and the like), it raises `PolicyViolation`.
- Otherwise it returns a **new dict containing only the allowlisted fields**,
  silently dropping everything else.

`transform()` lets a `PolicyViolation` **propagate** — it is fail-safe by
design and never swallows the error. Inside `FeedRunner.run_once()` that
propagation turns into a **recorded failure**: the run is marked unhealthy, the
output sink is never reached, and no personal data is ever written or
delivered. In other words, **if PII appears, the run fails** rather than leaking
it.

This makes the legal posture auditable: the field allowlist for each feed lives
in its config, and the guard that backs it lives in the code path every record
must pass through.
