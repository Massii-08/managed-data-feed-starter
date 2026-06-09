"""Core data models and the no-PII field policy for Feedsmith.

Defines the shared :class:`Record` dataclass, the :class:`FieldPolicy` that
enforces a strict no-PII rule on raw scraped data from public sources, and the
shared ISO-8601 UTC timestamp helper used across the package.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

# Field names that are considered personally identifiable information (PII).
# Any raw record containing one of these keys (compared case-insensitively) is
# rejected outright by :class:`FieldPolicy` so the feed only ever carries
# factual / non-PII data from public sources.
PII_FIELDS: frozenset = frozenset(
    {
        "name",
        "first_name",
        "last_name",
        "fullname",
        "email",
        "phone",
        "mobile",
        "address",
        "street",
        "ssn",
        "tax_id",
        "dob",
        "birthdate",
        "photo",
        "avatar",
        "ip",
        "ip_address",
        "user_id",
        "username",
        "profile_url",
    }
)


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with offset."""
    return datetime.now(timezone.utc).isoformat()


class PolicyViolation(Exception):
    """Raised when a raw record violates the no-PII field policy."""

    pass


@dataclass(frozen=True)
class Record:
    """A single clean, immutable feed record.

    Attributes:
        source: Identifier of the public source the data came from.
        fields: Mapping of allowed, non-PII field names to values.
        fetched_at: ISO-8601 UTC timestamp of when the data was fetched.
    """

    source: str
    fields: Dict[str, Any]
    fetched_at: str


class FieldPolicy:
    """Enforce a strict no-PII allow-list policy on raw records.

    The policy rejects any raw record containing a PII field name and otherwise
    keeps only the explicitly allowed keys, silently dropping everything else.
    """

    def __init__(self, allowed: Iterable[str], pii_fields: frozenset = PII_FIELDS) -> None:
        """Store the allowed field names and the set of forbidden PII fields."""
        self.allowed = set(allowed)
        self.pii_fields = pii_fields

    def validate(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a raw record against the no-PII policy.

        Raises:
            PolicyViolation: if any key (compared case-insensitively) is a PII
                field.

        Returns:
            A new dict containing only the keys present in ``self.allowed``.
            Keys that are neither PII nor allowed are silently dropped.
        """
        for key in raw:
            if key.lower() in self.pii_fields:
                raise PolicyViolation(
                    "PII field '{0}' is not allowed in this feed".format(key)
                )
        return {key: value for key, value in raw.items() if key in self.allowed}
