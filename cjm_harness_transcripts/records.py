"""The transcript record layer: tolerant JSONL loading + the append-only DAG.

A Claude Code transcript is an append-only DAG, never a linear log: every
addressable record carries a ``parentUuid``, a rewind never truncates the file
(post-rewind records append with an EARLIER parent, creating a fork), and
timestamps strictly increase — no regression signal exists. The ACTIVE path is
therefore a derived view: walk back from the tip (the newest main-chain
record is always on it). Empirical basis: the 2026-08-20 walkthrough sitting's
59-transcript scan (793 fork points) — DEC 671e9b11 point 8.

Loading is deliberately tolerant: the live transcript is appended by the
harness while a session runs, so a partially flushed final line is expected
and skipped, and non-addressable housekeeping records (``file-history-snapshot``,
``ai-title``, ``mode``, ...) are carried as raw records but excluded from the DAG.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TranscriptRecord:
    """One JSONL record, uuid-addressable or not, with the raw dict preserved."""
    type: str            # Record type: user / assistant / system / housekeeping kinds
    uuid: str | None     # Addressable identity (None on housekeeping records)
    parent_uuid: str | None  # The DAG edge; None on roots and housekeeping records
    timestamp: str | None    # ISO-8601 as recorded (UTC, trailing Z)
    is_sidechain: bool   # True on embedded sub-agent traffic — excluded from the main DAG
    raw: dict            # The full record, untouched


def load_records(path: str | Path) -> list[TranscriptRecord]:
    """Load a transcript JSONL tolerantly, in file order.

    Skips unparseable lines (the live file's partially flushed tail) and
    non-dict payloads; never raises on malformed content."""
    records: list[TranscriptRecord] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # partially flushed tail line of a live transcript
            if not isinstance(rec, dict):
                continue
            records.append(TranscriptRecord(
                type=rec.get("type", ""),
                uuid=rec.get("uuid"),
                parent_uuid=rec.get("parentUuid"),
                timestamp=rec.get("timestamp"),
                is_sidechain=bool(rec.get("isSidechain")),
                raw=rec,
            ))
    return records


@dataclass
class TranscriptDag:
    """The uuid-addressable view of a transcript: parent edges, forks, active path."""
    records: list[TranscriptRecord]
    by_uuid: dict[str, TranscriptRecord] = field(init=False)
    children: dict[str, list[TranscriptRecord]] = field(init=False)

    def __post_init__(self):
        self.by_uuid = {}
        self.children = {}
        for rec in self.records:
            if rec.uuid is None or rec.is_sidechain:
                continue
            self.by_uuid[rec.uuid] = rec
            if rec.parent_uuid is not None:
                self.children.setdefault(rec.parent_uuid, []).append(rec)

    @classmethod
    def load(cls, path: str | Path) -> "TranscriptDag":
        """Build the DAG straight from a transcript file."""
        return cls(load_records(path))

    def tip(self) -> TranscriptRecord | None:
        """The newest main-chain record — by construction always on the active path."""
        for rec in reversed(self.records):
            if rec.uuid is not None and not rec.is_sidechain:
                return rec
        return None

    def active_path(self) -> list[TranscriptRecord]:
        """The live conversation line, chronological: tip ancestry, forks excluded.

        Records down abandoned (rewound) branches are real discourse events and
        stay loaded — they are simply not on this walk. A cycle or a dangling
        parent ends the walk rather than raising (defensive: the file is
        external input)."""
        path: list[TranscriptRecord] = []
        seen: set[str] = set()
        rec = self.tip()
        while rec is not None and rec.uuid not in seen:
            seen.add(rec.uuid)
            path.append(rec)
            rec = self.by_uuid.get(rec.parent_uuid) if rec.parent_uuid else None
        path.reverse()
        return path

    def fork_points(self) -> dict[str, list[TranscriptRecord]]:
        """Parents with more than one child — rewind points and turn-internal forks."""
        return {p: kids for p, kids in self.children.items() if len(kids) > 1}
