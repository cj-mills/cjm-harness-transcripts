"""Mapping: session keys, boot info, and ranked transcript candidates."""

from datetime import timedelta, timezone

import pytest

from cjm_harness_transcripts.mapping import (
    MINT_SIGNAL,
    find_transcripts_for_key,
    parse_session_key,
    read_boot_info,
)

from conftest import rec, write_jsonl

KEY = "2026-08-20_17-05-20"


def iso_after(key, seconds):
    """A UTC record timestamp `seconds` after the (local) session key."""
    dt = parse_session_key(key) + timedelta(seconds=seconds)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def boot_transcript(tmp_path, name, key, delay, signal=True, text="Resume the project."):
    prose = f"{text} {MINT_SIGNAL}." if signal else text
    return write_jsonl(tmp_path / name, [
        {"type": "file-history-snapshot", "snapshot": {}},
        rec("user", "u1", None, ts=iso_after(key, delay), content=prose),
    ])


def test_parse_session_key_is_local_and_strict():
    dt = parse_session_key(KEY)
    assert dt.tzinfo is not None
    assert (dt.year, dt.hour, dt.second) == (2026, 17, 20)
    with pytest.raises(ValueError):
        parse_session_key("2026-08-20 17:05:20")


def test_read_boot_info_finds_first_user_prose(tmp_path):
    path = boot_transcript(tmp_path, "aaaa.jsonl", KEY, 90)
    boot = read_boot_info(path)
    assert boot.has_mint_signal and MINT_SIGNAL in boot.text


def test_candidates_ranked_by_delay_signal_first(tmp_path):
    boot_transcript(tmp_path, "11111111-aaaa-aaaa-aaaa-aaaaaaaaaaaa.jsonl", KEY, 3600)
    boot_transcript(tmp_path, "22222222-bbbb-bbbb-bbbb-bbbbbbbbbbbb.jsonl", KEY, 90)
    boot_transcript(tmp_path, "33333333-cccc-cccc-cccc-cccccccccccc.jsonl", KEY, -7200)  # before mint
    boot_transcript(tmp_path, "44444444-dddd-dddd-dddd-dddddddddddd.jsonl", KEY, 30, signal=False)

    matches = find_transcripts_for_key(tmp_path, KEY)
    assert [m.cc_session_uuid[:8] for m in matches] == ["22222222", "11111111"]
    assert matches[0].delay_seconds == pytest.approx(90, abs=1)

    loose = find_transcripts_for_key(tmp_path, KEY, require_signal=False)
    assert [m.cc_session_uuid[:8] for m in loose] == ["22222222", "11111111", "44444444"]
