"""Unit tests for the ST-LONG-01 measurement helpers (review R17 / R18). They live here,
not in test_live_long_session.py, because that file marks its whole run ``long``; these
helpers must be fast and always run."""
from test_live_long_session import edge_sets, minute_window


def _timing(at_ms):
    return {"capturedAtMs": at_ms}


def test_the_minute_window_is_bounded_on_both_ends():
    timings = {1: _timing(59_000), 2: _timing(60_000), 3: _timing(61_000)}
    assert [t["capturedAtMs"] for t in minute_window(timings, 60_000, 120_000)] == [60_000, 61_000]


def test_a_late_sample_never_counts_a_window_in_two_rows():
    timings = {1: _timing(59_500), 2: _timing(60_100)}
    first = minute_window(timings, 0, 60_000)
    second = minute_window(timings, 60_000, 120_000)
    assert [t["capturedAtMs"] for t in first] == [59_500]
    assert [t["capturedAtMs"] for t in second] == [60_100]
    assert {id(t) for t in first}.isdisjoint(id(t) for t in second)


def test_edge_sets_are_none_when_first_and_last_would_overlap():
    assert edge_sets([_timing(i) for i in range(1999)], 1000) is None


def test_edge_sets_are_disjoint_when_the_run_is_long_enough():
    timed = [_timing(i) for i in range(2000)]
    first, last = edge_sets(timed, 1000)
    assert len(first) == len(last) == 1000
    assert {id(t) for t in first}.isdisjoint(id(t) for t in last)
    assert first == timed[:1000] and last == timed[-1000:]
