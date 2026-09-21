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
    "task-notification",  # harness-authored; extracted separately as role="harness" (finding 47b83adb)
)
_WRAPPER_RE = re.compile(
    "|".join(rf"<{t}>.*?</{t}>" for t in _WRAPPER_TAGS), re.DOTALL
)
# The paste fence (Claude Code, sighted 2026-09-20; finding 984e56fd): text the user PASTES
# into the prompt arrives wrapped in a tag pair that BOTH carry the same random id. Unlike a
# wrapper block the inside IS the user's prose, so the fence is unwrapped, never dropped.
# Only the exact form matches — a fence the user merely quotes or escapes stays as written.
_PASTE_FENCE_RE = re.compile(r'<pasted_content id="([^"<>]+)">\n?(.*?)\n?</pasted_content id="\1">', re.DOTALL)

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

# The birth-class facet stamped on persisted THINKING SUMMARIES (item 6c3a0118):
# Claude Code 2.1.246+ stores a model-generated summary of a reasoning run as
# the thinking block's text (the client renders it "(summarized)"); earlier
# harness versions persisted thinking blocks EMPTY (signature only). No on-disk
# marker separates a summary from raw thinking — the harness never persists
# raw thinking, so any non-empty thinking text IS the displayed summary.
# Agent-origin (the model summarizing its own reasoning; the harness only
# stores it), so role stays "assistant" — the facet lets consumers style or
# filter it apart from authored prose.
THINKING_SUMMARY_SOURCE = "cc-thinking-summary"


@dataclass
class ExtractedMessage:
    """One user-facing message off the active path, ready to become a Message node."""
    role: str            # "user" | "assistant" | "harness"
    text: str            # Cleaned prose; raw markdown source on the assistant side
    timestamp: str | None    # ISO-8601 as recorded
    uuid: str            # Transcript identity (tool-param entries: the tool_use block id)
    parent_uuid: str | None  # DAG ancestry (NEXT edges mirror this succession)
    source: str | None = None  # Birth-class facet; None = plain transcript prose


def clean_user_text(text: str) -> str:
    """Strip harness wrapper blocks from a user prompt, unwrap paste fences (the inside
    is the user's own prose); collapse the scar tissue."""
    text = _WRAPPER_RE.sub("", text)
    text = _PASTE_FENCE_RE.sub(lambda m: m.group(2), text)
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


def _harness_notice(rec: TranscriptRecord) -> str | None:
    """A harness task-notification record's distilled summary, or None (finding 47b83adb).

    A record counts only when nothing but notification blocks remains after
    wrapper stripping — a (never-observed) mixed record stays a user message,
    its blocks stripped by _WRAPPER_RE. Multiple blocks join as one notice."""
    content = rec.raw.get("message", {}).get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "\n\n".join(b.get("text", "") for b in content
                           if isinstance(b, dict) and b.get("type") == "text")
    else:
        return None
    blocks = _TASK_NOTIFICATION_RE.findall(text)
    if not blocks or clean_user_text(text):
        return None
    summaries = []
    for block in blocks:
        m = _NOTIFICATION_SUMMARY_RE.search(block)
        summaries.append((m.group(1) if m else block).strip())
    return "\n\n".join(s for s in summaries if s) or None


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


def _thinking_summary_messages(rec: TranscriptRecord) -> list[ExtractedMessage]:
    """Messages for persisted thinking summaries (item 6c3a0118).

    One message per NON-EMPTY thinking block, block order — pre-2.1.246
    transcripts persisted thinking blocks empty and yield nothing here, so
    old eras need no backfill. Identity is the record uuid suffixed by the
    block index (the carrier record usually bears its own text message, so
    the bare uuid is taken — the tool-param convention); ancestry points at
    the carrier. Raw text verbatim, like assistant prose."""
    content = rec.raw.get("message", {}).get("content")
    if not isinstance(content, list):
        return []
    out: list[ExtractedMessage] = []
    for i, block in enumerate(content):
        if not (isinstance(block, dict) and block.get("type") == "thinking"):
            continue
        text = block.get("thinking")
        if not (isinstance(text, str) and text.strip()):
            continue
        out.append(ExtractedMessage(
            role="assistant", text=text.strip(), timestamp=rec.timestamp,
            uuid=f"{rec.uuid}#th{i}", parent_uuid=rec.uuid,
            source=THINKING_SUMMARY_SOURCE,
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
    its own TOOL_PARAM_SOURCE-faceted message after the record's text. Harness
    task-notification records (finding 47b83adb) extract as role="harness",
    HARNESS_SOURCE-faceted, distilled to the summary line."""
    table = TOOL_PARAM_PROSE if tool_params is None else tool_params
    messages: list[ExtractedMessage] = []
    for rec in dag.active_path():
        if rec.type == "user":
            notice = _harness_notice(rec)
            if notice is not None:
                messages.append(ExtractedMessage(
                    role="harness", text=notice, timestamp=rec.timestamp,
                    uuid=rec.uuid, parent_uuid=rec.parent_uuid,
                    source=HARNESS_SOURCE,
                ))
                continue
            text, extras = _user_prose(rec), []
        elif rec.type == "assistant":
            # Thinking summaries LEAD the record's prose (block order: the
            # thinking block precedes the text — item 6c3a0118); tool-param
            # prose trails it, as before. Succession follows this list order.
            messages.extend(_thinking_summary_messages(rec))
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


# Harness-authored task notifications (finding 47b83adb): background-task and
# agent completion notices land as role=user records but are authored by the
# harness — neither party's prose. They extract as role="harness" messages,
# text distilled to the <summary> line (an agent notice's <result> payload is
# harness plumbing; the assistant's relay turn carries what mattered).
HARNESS_SOURCE = "cc-harness"
_TASK_NOTIFICATION_RE = re.compile(
    r"<task-notification>(.*?)</task-notification>", re.DOTALL
)
_NOTIFICATION_SUMMARY_RE = re.compile(r"<summary>(.*?)</summary>", re.DOTALL)
