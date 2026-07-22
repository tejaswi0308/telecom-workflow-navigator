"""
Dedicated conversation memory module for the Telecom Workflow Navigator.

This module owns ALL conversation memory concerns — where it's stored, how
it's loaded/saved, how much history is kept, and how it's formatted for the
LLM prompt. Previously this logic was mixed directly inside rag.py alongside
retrieval and generation code; it's extracted here so memory can be reasoned
about, tested, and changed (e.g. swapped for Redis/a DB later) independently
of the RAG pipeline itself.

Storage model: one JSON file per session, under memory/rag_memory_<session_id>.json.
Each file holds a list of {"user": ..., "assistant": ...} turn dicts, capped
at MEMORY_TURNS entries (oldest turns drop off first).
"""

import json
import os
import re
from pathlib import Path

MEMORY_TURNS = int(os.getenv("MEMORY_TURNS", "6"))

_SAFE_SESSION_ID_RE = re.compile(r"[^A-Za-z0-9_-]")


def _sanitize_session_id(session_id: str) -> str:
    """
    Prevents path traversal / invalid filenames. Falls back to 'default'
    if the sanitized id is empty.
    """
    cleaned = _SAFE_SESSION_ID_RE.sub("_", str(session_id or "").strip())
    return cleaned or "default"


def memory_dir_path() -> Path:
    directory = Path(__file__).resolve().parent / "memory"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def memory_file_path(session_id: str = "default") -> Path:
    safe_id = _sanitize_session_id(session_id)
    return memory_dir_path() / f"rag_memory_{safe_id}.json"


def load_chat_memory(session_id: str = "default") -> list[dict[str, str]]:
    """
    Loads up to the last MEMORY_TURNS turns for this session.
    Returns [] for a brand-new session, a missing/corrupt file, or a
    malformed file — never raises, since "no memory" is always a valid,
    safe state (this is what makes the no-history guardrail in
    guardrails.py trustworthy: an empty list here always means "genuinely
    no prior conversation", not "something broke").
    """
    path = memory_file_path(session_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    turns: list[dict[str, str]] = []
    for item in data[-MEMORY_TURNS:]:
        if isinstance(item, dict) and "user" in item and "assistant" in item:
            turns.append({"user": str(item["user"]), "assistant": str(item["assistant"])})
    return turns


def save_chat_memory(turns: list[dict[str, str]], session_id: str = "default") -> None:
    """Persists up to the last MEMORY_TURNS turns for this session."""
    path = memory_file_path(session_id)
    path.write_text(json.dumps(turns[-MEMORY_TURNS:], indent=2), encoding="utf-8")


def append_turn(session_id: str, user_question: str, assistant_answer: str) -> list[dict[str, str]]:
    """
    Convenience helper: loads existing history, appends one new turn, saves,
    and returns the updated history — so callers don't have to manually
    juggle load/append/save every time a turn completes.
    """
    history = load_chat_memory(session_id)
    history.append({"user": user_question, "assistant": assistant_answer})
    save_chat_memory(history, session_id)
    return history


def format_chat_history(turns: list[dict[str, str]]) -> str:
    """Formats memory turns into the block injected into the LLM prompt."""
    if not turns:
        return "No previous conversation."
    sections = []
    for index, turn in enumerate(turns, start=1):
        sections.append(f"Turn {index}\nUser: {turn['user']}\nAssistant: {turn['assistant']}")
    return "\n\n".join(sections)


def has_history(session_id: str = "default") -> bool:
    """True if this session has at least one prior turn. Used by guardrails
    to decide whether a follow-up/context-dependent question can be safely
    answered, or must be refused as having no valid prior context."""
    return len(load_chat_memory(session_id)) > 0