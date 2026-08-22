# cjm-harness-transcripts

<!-- generated from the context graph by `cjm-context-graph readme` — do not edit by hand; edit the graph (the urge to hand-edit = move it on-graph) -->

_No purpose recorded on-graph yet — author it with_ `assert 64d33989-f107-5495-ad93-45aff3dcf5ef purpose "…"` _(or by the repo's entity key)._

## Modules

- **`cjm_harness_transcripts`** — cjm-harness-transcripts: parse agent-harness session transcripts (Claude Code
- **`cjm_harness_transcripts.extract`** — User-facing prose extraction — both sides, one truth.
- **`cjm_harness_transcripts.mapping`** — Transcript ↔ session-key mapping, derived at pull time.
- **`cjm_harness_transcripts.records`** — The transcript record layer: tolerant JSONL loading + the append-only DAG.

## API

### `cjm_harness_transcripts.extract`

- `ExtractedMessage` _class_ — One user-facing message off the active path, ready to become a Message node.
- `clean_user_text` _function_ — Strip harness wrapper blocks from a user prompt; collapse the scar tissue.
- `extract_messages` _function_ — The active path's user-facing messages, chronological.

### `cjm_harness_transcripts.mapping`

- `BootInfo` _class_ — The first user prose of a transcript — the mapping's evidence.
- `TranscriptMatch` _class_ — One ranked candidate pairing for a session key.
- `find_transcripts_for_key` _function_ — All plausible transcripts for a session key, best first.
- `parse_record_timestamp` _function_ — A transcript record timestamp (ISO-8601, trailing Z) as an aware datetime.
- `parse_session_key` _function_ — A session key (local start timestamp, e.g. 2026-08-20_17-05-20) as an aware datetime.
- `read_boot_info` _function_ — The transcript's first user record bearing prose, or None (empty/tool-only file).

### `cjm_harness_transcripts.records`

- `TranscriptDag` _class_ — The uuid-addressable view of a transcript: parent edges, forks, active path.
- `TranscriptRecord` _class_ — One JSONL record, uuid-addressable or not, with the raw dict preserved.
- `load_records` _function_ — Load a transcript JSONL tolerantly, in file order.

## Dependencies

**Used by:** `cjm-context-graph-projection`
