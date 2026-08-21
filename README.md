# cjm-harness-transcripts

Parse agent-harness session transcripts (Claude Code JSONL first) into their
append-only record DAG, walk the active path past rewinds, extract the
user-facing prose on both sides, and derive the transcript ↔ on-graph
session-key mapping.

Pure-parse and dependency-free: the graph-minting half of the pull path lives
with the projection verbs, which import this lib. One extraction truth, three
consumers — the live scratchpad pull, the archive-absorb instrument, and the
housekeeping miner.

Design authority: the scratchpad-v2 pass DECs (data model `91c47b4a`,
message-pull `fc6a0cdc`, presentation/transcript-DAG `671e9b11`, rungs
`e8b2f397`) on the cjm-substrate dev graph.
