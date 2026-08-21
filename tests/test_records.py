"""The record layer: tolerant loading + DAG walks over rewind forks."""

from cjm_harness_transcripts.records import TranscriptDag, load_records

from conftest import rec


def test_load_tolerates_garbage_and_partial_tail(make_transcript):
    path = make_transcript(
        [rec("user", "u1", None, ts="2026-08-20T22:00:00.000Z", content="hi")],
        tail='{"type": "assistant", "uuid": "trunc',  # live-file partially flushed line
    )
    path.write_text(path.read_text() + "\nnot json at all\n[1, 2, 3]\n", encoding="utf-8")
    records = load_records(path)
    assert [r.uuid for r in records] == ["u1"]


def test_housekeeping_records_load_but_stay_off_the_dag(make_transcript):
    path = make_transcript([
        {"type": "file-history-snapshot", "snapshot": {}},
        rec("user", "u1", None, ts="2026-08-20T22:00:00.000Z", content="hi"),
        {"type": "ai-title", "title": "x"},
    ])
    dag = TranscriptDag.load(path)
    assert len(dag.records) == 3
    assert set(dag.by_uuid) == {"u1"}


def test_active_path_follows_tip_ancestry_past_a_rewind(make_transcript):
    # u1 -> a1 -> u2a (abandoned) ; rewind: u2b appends later with parent a1
    path = make_transcript([
        rec("user", "u1", None, ts="2026-08-20T22:00:00.000Z", content="q"),
        rec("assistant", "a1", "u1", ts="2026-08-20T22:00:05.000Z", content=[{"type": "text", "text": "r"}]),
        rec("user", "u2a", "a1", ts="2026-08-20T22:01:00.000Z", content="first try"),
        rec("assistant", "a2a", "u2a", ts="2026-08-20T22:01:05.000Z", content=[{"type": "text", "text": "dead"}]),
        rec("user", "u2b", "a1", ts="2026-08-20T22:02:00.000Z", content="second try"),
        rec("assistant", "a2b", "u2b", ts="2026-08-20T22:02:05.000Z", content=[{"type": "text", "text": "live"}]),
    ])
    dag = TranscriptDag.load(path)
    assert dag.tip().uuid == "a2b"
    assert [r.uuid for r in dag.active_path()] == ["u1", "a1", "u2b", "a2b"]
    assert set(dag.fork_points()) == {"a1"}


def test_sidechain_records_never_become_tip_or_path(make_transcript):
    path = make_transcript([
        rec("user", "u1", None, ts="2026-08-20T22:00:00.000Z", content="q"),
        rec("assistant", "a1", "u1", ts="2026-08-20T22:00:05.000Z", content=[{"type": "text", "text": "r"}]),
        rec("user", "s1", "a1", ts="2026-08-20T22:00:06.000Z", content="agent brief", sidechain=True),
        rec("assistant", "s2", "s1", ts="2026-08-20T22:00:07.000Z", content=[{"type": "text", "text": "agent reply"}], sidechain=True),
    ])
    dag = TranscriptDag.load(path)
    assert dag.tip().uuid == "a1"
    assert [r.uuid for r in dag.active_path()] == ["u1", "a1"]


def test_dangling_parent_ends_walk_instead_of_raising(make_transcript):
    path = make_transcript([
        rec("assistant", "a9", "missing-parent", ts="2026-08-20T22:00:00.000Z",
            content=[{"type": "text", "text": "orphan"}]),
    ])
    assert [r.uuid for r in TranscriptDag.load(path).active_path()] == ["a9"]
