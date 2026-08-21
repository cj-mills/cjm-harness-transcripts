"""User-facing prose extraction — both sides, one truth.

Filters a transcript's active path down to what the humans actually read:
assistant text blocks (no thinking, no tool calls/results) and user prompts
(minus harness wrappers — caveat blocks, system reminders, command noise).
The transcript stores assistant messages as RAW MARKDOWN SOURCE (rendering is
client-layered — verified DEC 671e9b11 point 9), so extracted text is the
authoritative body for a Message node, not a rendering of it.

This module is consumed identically by the live scratchpad pull, the
archive-absorb instrument, and the housekeeping miner (DEC e8b2f397 point 2).
"""

import re
from dataclasses import dataclass

from .records import TranscriptDag, TranscriptRecord

# Harness-injected wrapper blocks that are not the user's own prose.
_WRAPPER_TAGS = (
    "local-command-caveat",
    "system-reminder",
    "command-name",
    "command-message",
    "command-args",
    "command-contents",
    "local-command-stdout",
    "local-command-stderr",
)
_WRAPPER_RE = re.compile(
    "|".join(rf"<{t}>.*?</{t}>" for t in _WRAPPER_TAGS), re.DOTALL
)


@dataclass
class ExtractedMessage:
    """One user-facing message off the active path, ready to become a Message node."""
    role: str            # "user" | "assistant"
    text: str            # Cleaned prose; raw markdown source on the assistant side
    timestamp: str | None    # ISO-8601 as recorded
    uuid: str            # The record's transcript identity
    parent_uuid: str | None  # DAG ancestry (NEXT edges mirror this succession)


def clean_user_text(text: str) -> str:
    """Strip harness wrapper blocks from a user prompt; collapse the scar tissue."""
    text = _WRAPPER_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _user_prose(rec: TranscriptRecord) -> str | None:
    """A user record's own prose, or None when the record is tool/housekeeping traffic."""
    content = rec.raw.get("message", {}).get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        if not parts:
            return None  # tool_result-only record
        text = "\n\n".join(parts)
    else:
        return None
    cleaned = clean_user_text(text)
    return cleaned or None


def _assistant_prose(rec: TranscriptRecord) -> str | None:
    """An assistant record's text blocks (raw markdown), or None on tool-only records."""
    content = rec.raw.get("message", {}).get("content")
    if not isinstance(content, list):
        return None
    parts = [b.get("text", "") for b in content
             if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]
    text = "\n\n".join(parts).strip()
    return text or None


def extract_messages(dag: TranscriptDag) -> list[ExtractedMessage]:
    """The active path's user-facing messages, chronological.

    One ExtractedMessage per prose-bearing record: an assistant turn that
    interleaves status prose between tool calls yields one message per text
    record, exactly as the client displayed them."""
    messages: list[ExtractedMessage] = []
    for rec in dag.active_path():
        if rec.type == "user":
            text = _user_prose(rec)
        elif rec.type == "assistant":
            text = _assistant_prose(rec)
        else:
            continue
        if text is None:
            continue
        messages.append(ExtractedMessage(
            role=rec.type,
            text=text,
            timestamp=rec.timestamp,
            uuid=rec.uuid,
            parent_uuid=rec.parent_uuid,
        ))
    return messages
