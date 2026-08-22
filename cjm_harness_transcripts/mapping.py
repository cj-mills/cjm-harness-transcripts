"""Transcript ↔ session-key mapping, derived at pull time.

The workbench cannot record the pairing at mint: the Claude Code session
starts strictly AFTER the on-graph Shift+S mint, so the CC session UUID does
not exist yet (DEC fc6a0cdc point 1, superseding the record-at-mint variant).
What IS derivable: the minted session's boot prompt carries the
minted-in-workbench resume signal, session keys are local start timestamps,
and every transcript record is UTC-stamped. So: scan the project's transcript
dir, prefer boot records carrying the mint signal, and rank candidates by how
closely their boot time follows the key. The caller records the winning
pairing as a fact on the Session node — derived once, read thereafter.

Multiple transcripts may legitimately follow one key (a Claude Code restart
resumes the same on-graph session), so this module returns ALL candidates
ranked, never a single guess.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .records import load_records

# The boot-prompt signal the session-start ritual includes for minted sessions
# — a PREFIX, substring-matched, so every minting seat qualifies ("…minted
# in-workbench", "…minted in-scratchpad") and every legacy boot still carries it.
MINT_SIGNAL = "New session minted in-"

_KEY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")

# Boot-time slack: the boot record must not predate the mint by more than this
# (small negative tolerance absorbs sub-second clock jitter, nothing more).
_SLACK_SECONDS = 60.0


def parse_session_key(key: str) -> datetime:
    """A session key (local start timestamp, e.g. 2026-08-20_17-05-20) as an aware datetime."""
    if not _KEY_RE.match(key):
        raise ValueError(f"not a session key: {key!r}")
    naive = datetime.strptime(key, "%Y-%m-%d_%H-%M-%S")
    return naive.astimezone()  # interpret in the local timezone, the key's home


def parse_record_timestamp(ts: str) -> datetime:
    """A transcript record timestamp (ISO-8601, trailing Z) as an aware datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


@dataclass
class BootInfo:
    """The first user prose of a transcript — the mapping's evidence."""
    text: str
    timestamp: datetime
    has_mint_signal: bool


def read_boot_info(path: str | Path) -> BootInfo | None:
    """The transcript's first user record bearing prose, or None (empty/tool-only file)."""
    for rec in load_records(path):
        if rec.type != "user" or rec.is_sidechain or rec.timestamp is None:
            continue
        content = rec.raw.get("message", {}).get("content")
        if not isinstance(content, str):
            continue
        return BootInfo(
            text=content,
            timestamp=parse_record_timestamp(rec.timestamp),
            has_mint_signal=MINT_SIGNAL in content,
        )
    return None


@dataclass
class TranscriptMatch:
    """One ranked candidate pairing for a session key."""
    path: Path
    cc_session_uuid: str     # The transcript's filename stem IS the CC session UUID
    boot: BootInfo
    delay_seconds: float     # Boot time minus mint time; small = started right after mint


def find_transcripts_for_key(
    transcript_dir: str | Path, session_key: str, *, require_signal: bool = True,
) -> list[TranscriptMatch]:
    """All plausible transcripts for a session key, best first.

    A transcript qualifies when its boot prose follows the mint time (within
    slack) — and, by default, carries the mint signal; pass
    ``require_signal=False`` to also rank signal-less candidates (resumed or
    manually booted sessions). Ordering: signal-bearing first, then smallest
    delay after the mint."""
    key_dt = parse_session_key(session_key)
    matches: list[TranscriptMatch] = []
    for path in Path(transcript_dir).glob("*.jsonl"):
        boot = read_boot_info(path)
        if boot is None:
            continue
        delay = (boot.timestamp - key_dt).total_seconds()
        if delay < -_SLACK_SECONDS:
            continue  # booted before the mint — a different session
        if require_signal and not boot.has_mint_signal:
            continue
        matches.append(TranscriptMatch(
            path=path, cc_session_uuid=path.stem, boot=boot, delay_seconds=delay,
        ))
    matches.sort(key=lambda m: (not m.boot.has_mint_signal, m.delay_seconds))
    return matches
