"""Extraction: user-facing prose both sides, wrappers stripped, tool traffic dropped."""

from cjm_harness_transcripts.extract import clean_user_text, extract_messages
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
