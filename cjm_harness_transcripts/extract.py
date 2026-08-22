"""User-facing prose extraction — both sides, one truth.

Filters a transcript's active path down to what the humans actually read:
assistant text blocks (no thinking, no tool calls/results), user prompts
(minus harness wrappers — caveat blocks, system reminders, command noise),
and the curated tool parameters the client renders as discourse
(TOOL_PARAM_PROSE — a SendUserFile caption is prose living in tool_use
input; finding 60d719fe).
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

# Tool parameters that carry user-facing prose (finding 60d719fe): the client
# renders these as discourse (a SendUserFile caption rides the file card), but
# the record holds only a tool_use block, so text-block extraction misses them.
# Curated allowlist: tool name -> dotted paths into the tool_use input.
TOOL_PARAM_PROSE: dict[str, tuple[str, ...]] = {
    "SendUserFile": ("caption",),
}

# The birth-class facet stamped on tool-param messages (one label, many sources
# — DEC 91c47b4a pt 1; graph-side consumers mirror the literal).
TOOL_PARAM_SOURCE = "cc-tool-param"


@dataclass
class ExtractedMessage:
    """One user-facing message off the active path, ready to become a Message node."""
    role: str            # "user" | "assistant"
    text: str            # Cleaned prose; raw markdown source on the assistant side
    timestamp: str | None    # ISO-8601 as recorded
    uuid: str            # Transcript identity (tool-param entries: the tool_use block id)
    parent_uuid: str | None  # DAG ancestry (NEXT edges mirror this succession)
    source: str | None = None  # Birth-class facet; None = plain transcript prose


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


def _tool_param_messages(
    rec: TranscriptRecord,
    table: dict[str, tuple[str, ...]],  # tool name -> dotted paths into tool_use input
) -> list[ExtractedMessage]:
    """Messages for user-facing prose carried in tool parameters (finding 60d719fe).

    One message per prose-bearing (tool_use block, path) hit, block order.
    Identity is the block id (the carrier record may also bear its own text
    message, so the record uuid is taken); ancestry points at the carrier."""
    content = rec.raw.get("message", {}).get("content")
    if not isinstance(content, list):
        return []
    out: list[ExtractedMessage] = []
    for i, block in enumerate(content):
        if not (isinstance(block, dict) and block.get("type") == "tool_use"):
            continue
        for path in table.get(block.get("name", ""), ()):
            value = block.get("input")
            for part in path.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if not (isinstance(value, str) and value.strip()):
                continue
            out.append(ExtractedMessage(
                role="assistant", text=value.strip(), timestamp=rec.timestamp,
                uuid=block.get("id") or f"{rec.uuid}#tp{i}", parent_uuid=rec.uuid,
                source=TOOL_PARAM_SOURCE,
            ))
    return out


def extract_messages(
    dag: TranscriptDag,
    *,
    tool_params: dict[str, tuple[str, ...]] | None = None,  # None = the curated TOOL_PARAM_PROSE table; {} disables
) -> list[ExtractedMessage]:
    """The active path's user-facing messages, chronological.

    One ExtractedMessage per prose-bearing record: an assistant turn that
    interleaves status prose between tool calls yields one message per text
    record, exactly as the client displayed them. Prose the client renders out
    of tool_use parameters (the curated table — finding 60d719fe) extracts as
    its own TOOL_PARAM_SOURCE-faceted message after the record's text."""
    table = TOOL_PARAM_PROSE if tool_params is None else tool_params
    messages: list[ExtractedMessage] = []
    for rec in dag.active_path():
        if rec.type == "user":
            text, extras = _user_prose(rec), []
        elif rec.type == "assistant":
            text, extras = _assistant_prose(rec), _tool_param_messages(rec, table)
        else:
            continue
        if text is not None:
            messages.append(ExtractedMessage(
                role=rec.type,
                text=text,
                timestamp=rec.timestamp,
                uuid=rec.uuid,
                parent_uuid=rec.parent_uuid,
            ))
        messages.extend(extras)
    return messages
