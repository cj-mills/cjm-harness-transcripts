"""Extraction: user-facing prose both sides, wrappers stripped, tool traffic dropped."""

from cjm_harness_transcripts.extract import (
    TOOL_PARAM_SOURCE, clean_user_text, extract_messages)
from cjm_harness_transcripts.records import TranscriptDag

from conftest import rec


def test_clean_user_text_strips_harness_wrappers():
    raw = (
        "<local-command-caveat>Caveat: local commands.</local-command-caveat>\n"
        "Real question here.\n\n"
        "<system-reminder>\nbackground noise\n</system-reminder>\n"
    )
    assert clean_user_text(raw) == "Real question here."


def test_clean_user_text_strips_command_wrappers():
    raw = "<command-name>/foo</command-name>\n<command-args>bar</command-args>\n"
    assert clean_user_text(raw) == ""


def test_extract_keeps_both_sides_and_drops_tool_traffic(make_transcript):
    path = make_transcript([
        rec("user", "u1", None, ts="2026-08-20T22:00:00.000Z",
            content="<system-reminder>ctx</system-reminder>\nHello there"),
        rec("assistant", "a1", "u1", ts="2026-08-20T22:00:03.000Z",
            content=[{"type": "text", "text": "Looking now."},
                     {"type": "tool_use", "name": "Bash", "input": {}}]),
        rec("user", "t1", "a1", ts="2026-08-20T22:00:04.000Z",
            content=[{"type": "tool_result", "content": "output"}]),
        rec("assistant", "a2", "t1", ts="2026-08-20T22:00:08.000Z",
            content=[{"type": "thinking", "thinking": "private"},
                     {"type": "text", "text": "**Found it.**"}]),
    ])
    messages = extract_messages(TranscriptDag.load(path))
    assert [(m.role, m.text) for m in messages] == [
        ("user", "Hello there"),
        ("assistant", "Looking now."),
        ("assistant", "**Found it.**"),  # raw markdown source, verbatim
    ]
    assert messages[0].uuid == "u1" and messages[0].parent_uuid is None


def test_extract_skips_abandoned_branch_messages(make_transcript):
    path = make_transcript([
        rec("user", "u1", None, ts="2026-08-20T22:00:00.000Z", content="q"),
        rec("user", "u2a", "u1", ts="2026-08-20T22:01:00.000Z", content="retracted"),
        rec("user", "u2b", "u1", ts="2026-08-20T22:02:00.000Z", content="final form"),
    ])
    messages = extract_messages(TranscriptDag.load(path))
    assert [m.text for m in messages] == ["q", "final form"]


def test_tool_only_and_empty_records_yield_nothing(make_transcript):
    path = make_transcript([
        rec("user", "u1", None, ts="2026-08-20T22:00:00.000Z",
            content="<local-command-caveat>only wrapper</local-command-caveat>"),
        rec("assistant", "a1", "u1", ts="2026-08-20T22:00:03.000Z",
            content=[{"type": "tool_use", "name": "Bash", "input": {}}]),
    ])
    assert extract_messages(TranscriptDag.load(path)) == []


def test_tool_param_prose_extracts_as_faceted_message(make_transcript):
    # The finding-60d719fe class: a SendUserFile caption is user-facing prose
    # living in tool_use input — it becomes its own message, block-id identity,
    # cc-tool-param facet, after the carrier record's own text.
    path = make_transcript([
        rec("user", "u1", None, ts="2026-08-21T21:00:00.000Z", content="ship it"),
        rec("assistant", "a1", "u1", ts="2026-08-21T21:00:05.000Z",
            content=[{"type": "text", "text": "Exporting now."},
                     {"type": "tool_use", "id": "toolu_1", "name": "SendUserFile",
                      "input": {"files": ["report.md"],
                                "caption": "Here's the exported report."}}]),
    ])
    messages = extract_messages(TranscriptDag.load(path))
    assert [(m.role, m.text) for m in messages] == [
        ("user", "ship it"),
        ("assistant", "Exporting now."),
        ("assistant", "Here's the exported report."),
    ]
    caption = messages[-1]
    assert caption.uuid == "toolu_1" and caption.parent_uuid == "a1"
    assert caption.source == TOOL_PARAM_SOURCE
    assert messages[0].source is None and messages[1].source is None


def test_tool_param_table_is_curated_and_optional(make_transcript):
    # Blank/absent params and unlisted tools yield nothing; tool_params={}
    # disables the lane outright.
    quiet = make_transcript([
        rec("assistant", "a1", None, ts="2026-08-21T21:00:00.000Z",
            content=[{"type": "tool_use", "id": "t1", "name": "SendUserFile",
                      "input": {"files": ["x"], "caption": "  "}},
                     {"type": "tool_use", "id": "t2", "name": "Bash",
                      "input": {"command": "ls"}},
                     {"type": "tool_use", "id": "t3", "name": "SendUserFile",
                      "input": {"files": ["y"]}}]),
    ])
    assert extract_messages(TranscriptDag.load(quiet)) == []
    captioned = make_transcript([
        rec("assistant", "a1", None, ts="2026-08-21T21:00:09.000Z",
            content=[{"type": "tool_use", "id": "t4", "name": "SendUserFile",
                      "input": {"caption": "real"}}]),
    ], name="bbbb1111-2222-3333-4444-555566667777.jsonl")
    assert [m.text for m in extract_messages(TranscriptDag.load(captioned))] == ["real"]
    assert extract_messages(TranscriptDag.load(captioned), tool_params={}) == []
