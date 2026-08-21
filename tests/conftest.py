"""Synthetic-transcript fixtures: build JSONL records the way the harness writes them."""

import json

import pytest


def rec(type_, uuid_=None, parent=None, ts=None, content=None, sidechain=False, **extra):
    """One transcript record dict; content str = user prose, list = content blocks."""
    r = {"type": type_, "isSidechain": sidechain, **extra}
    if uuid_ is not None:
        r["uuid"] = uuid_
        r["parentUuid"] = parent
    if ts is not None:
        r["timestamp"] = ts
    if content is not None:
        r["message"] = {"role": type_, "content": content}
    return r


def write_jsonl(path, records, tail=""):
    """Write records as JSONL, optionally with a partially flushed tail line."""
    lines = [json.dumps(r) for r in records]
    text = "\n".join(lines) + "\n" + tail
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def make_transcript(tmp_path):
    """Factory: write a synthetic transcript and return its path."""
    def _make(records, name="aaaa1111-2222-3333-4444-555566667777.jsonl", tail=""):
        return write_jsonl(tmp_path / name, records, tail=tail)
    return _make
