"""
Entity Memory — tracks active customer + intent across conversation turns.

Like a mechanic's job card: once you've established WHO the customer is,
every follow-up question ("check it again", "what are her loans?") can
resolve to that same customer without re-asking.

Storage: piggybacks on the existing sessions table via a special
'entity_state' message type in the messages JSON array. No new DB table needed.

EntityState fields:
  customer_id   — resolved DB customer ID
  customer_name — full name for display
  last_intent   — last classified RAG intent (customer/loan/fraud/etc.)
  last_topic    — brief summary of last question topic
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from typing import List, Optional

from src.api.memory import get_memory


# ── State container ───────────────────────────────────────────────────────────

@dataclass
class EntityState:
    customer_id:   Optional[str] = None
    customer_name: Optional[str] = None
    last_intent:   Optional[str] = None
    last_topic:    Optional[str] = None

    def has_customer(self) -> bool:
        return bool(self.customer_id)

    def is_empty(self) -> bool:
        return not any([self.customer_id, self.customer_name, self.last_intent])

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "EntityState":
        return EntityState(
            customer_id   = d.get("customer_id"),
            customer_name = d.get("customer_name"),
            last_intent   = d.get("last_intent"),
            last_topic    = d.get("last_topic"),
        )


# ── Public API ────────────────────────────────────────────────────────────────

def get_entity_state(session_id: str) -> EntityState:
    """
    Read the latest entity state for this session.
    Scans messages in reverse to find the most recent 'entity_state' record.
    Falls back to scanning message content for customer mentions if no
    explicit entity_state record exists yet.
    """
    mem      = get_memory()
    history  = mem.get_session_history(session_id)

    # Fast path: find explicit entity_state message (written by update_entity_state)
    for msg in reversed(history):
        if msg.get("role") == "entity_state":
            return EntityState.from_dict(msg.get("state", {}))

    # Fallback: scan message content for customer_id patterns
    return _infer_entity_state_from_history(history)


def update_entity_state(
    session_id:    str,
    customer_id:   Optional[str] = None,
    customer_name: Optional[str] = None,
    last_intent:   Optional[str] = None,
    last_topic:    Optional[str] = None,
) -> EntityState:
    """
    Persist updated entity state into the session's message history.
    Only updates fields that are explicitly provided (None = keep existing).
    """
    mem      = get_memory()
    existing = get_entity_state(session_id)

    new_state = EntityState(
        customer_id   = customer_id   or existing.customer_id,
        customer_name = customer_name or existing.customer_name,
        last_intent   = last_intent   or existing.last_intent,
        last_topic    = last_topic    or existing.last_topic,
    )

    # Store as a special message type so get_session_history() can scan it
    entity_msg = {
        "role":      "entity_state",
        "state":     new_state.to_dict(),
        "timestamp": _now(),
    }

    # Directly write to session messages via SessionMemory internals
    history = mem.get_session_history(session_id)
    # Replace the most recent entity_state record if one exists;
    # otherwise append a new one. This keeps the messages array compact.
    replaced = False
    for i in range(len(history) - 1, -1, -1):
        if history[i].get("role") == "entity_state":
            history[i] = entity_msg
            replaced = True
            break
    if not replaced:
        history.append(entity_msg)

    _write_messages(session_id, history)
    return new_state


def clear_entity_state(session_id: str) -> None:
    """Remove entity state (e.g., banker switches to a different customer)."""
    mem     = get_memory()
    history = [
        m for m in mem.get_session_history(session_id)
        if m.get("role") != "entity_state"
    ]
    _write_messages(session_id, history)


def resolve_customer_id(
    request_customer_id: Optional[str],
    session_id: str,
) -> Optional[str]:
    """
    Return the best-available customer_id for this request:
      1. Explicit ID in the current request (highest priority)
      2. Active customer in session entity memory
      3. None (truly unknown)
    """
    if request_customer_id:
        return request_customer_id
    state = get_entity_state(session_id)
    return state.customer_id


# ── Helpers ───────────────────────────────────────────────────────────────────

_CUSTOMER_ID_RE = re.compile(
    r"(?:customer[_\s]?id|cid|id)[:\s]+([a-zA-Z0-9_-]{4,})",
    re.IGNORECASE,
)
_CUSTOMER_NAME_RE = re.compile(
    r"(?:customer|client)[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)",
)


def _infer_entity_state_from_history(history: List[dict]) -> EntityState:
    """
    Best-effort entity extraction when no explicit entity_state record exists.
    Scans the last 6 messages for customer ID / name patterns.
    """
    state = EntityState()
    for msg in reversed(history[-6:]):
        content = msg.get("content", "")
        if not content or msg.get("role") == "entity_state":
            continue
        if not state.customer_id:
            m = _CUSTOMER_ID_RE.search(content)
            if m:
                state.customer_id = m.group(1)
        if not state.customer_name:
            m = _CUSTOMER_NAME_RE.search(content)
            if m:
                state.customer_name = m.group(1)
        if state.customer_id and state.customer_name:
            break
    return state


def _write_messages(session_id: str, messages: list) -> None:
    """Write raw messages list back to the sessions table."""
    from src.models.database import engine
    from sqlalchemy import text
    from datetime import datetime

    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE sessions SET messages = :msgs, updated_at = :now
            WHERE session_id = :sid
        """), {
            "msgs": json.dumps(messages),
            "now":  datetime.utcnow().isoformat(),
            "sid":  session_id,
        })
        conn.commit()


def _now() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat()
