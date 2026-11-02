"""Per-request stage timings for ``POST /infer``, reported as a ``Server-Timing`` header.

Why a header and not a field of the stored record: the commit stage can only be timed
AFTER ``db.commit()``, and by then the record it would describe is already durable. The
header is the one place that can carry it.

What each segment covers (milliseconds, wall clock, ``time.perf_counter``):

``preprocess``  decode + resize + normalise the frame (the provider's own ``preprocess_ms``)
``vision``      the ONNX forward pass          (``vision_ms``)
``telemetry``   the XGBoost prediction         (``telemetry_ms``)
``fusion``      ``inference.run_inference``: freshness, EMA, fusion, level, alert FSM
``commit``      ``db.commit()`` of the new record, and nothing else
``total``       the whole route handler: session lookup, idempotency check, models,
                persistence, commit, cache. NOT request parsing / validation (before the
                handler) and NOT response serialisation (after it).

``preprocess`` / ``vision`` / ``telemetry`` come from the provider; a branch that had no
input did not run, so it is reported as ``dur=0.00;desc="skipped"`` rather than omitted.
A request answered from the stored record (an idempotent re-send) did none of the work:
it carries ``total`` only.

``latency_ms`` in the stored record is a DIFFERENT, older number and keeps its meaning: it
runs from the start of the handler to the moment the fused record is built, so it ends
BEFORE ``db.commit()`` and excludes the commit and the cache write. ``Server-Timing: total``
is always >= ``latency_ms`` (to rounding); the difference is the persistence cost.
"""
import time
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar

SEGMENTS = ("preprocess", "vision", "telemetry", "fusion", "commit", "total")


def format_server_timing(durations_ms: Mapping[str, float], skipped: Iterable[str] = ()) -> str:
    """``Server-Timing`` header value for the segments in ``durations_ms``, always in the
    canonical order. A name outside ``SEGMENTS`` is a programming error, not data."""
    unknown = (set(durations_ms) | set(skipped)) - set(SEGMENTS)
    if unknown:
        raise ValueError(f"unknown Server-Timing segment(s): {sorted(unknown)}")
    skipped = set(skipped)
    parts = []
    for name in SEGMENTS:
        if name in durations_ms:
            piece = f"{name};dur={max(0.0, durations_ms[name]):.2f}"
            if name in skipped:
                piece += ';desc="skipped"'
            parts.append(piece)
    return ", ".join(parts)


class SegmentTimer:
    """Collects the segments of one request. Created by the route, filled by the code it
    calls, formatted by the route; code that is not timed (the replay route) passes None."""

    def __init__(self):
        self.ms: dict[str, float] = {}
        self.skipped: set[str] = set()

    @contextmanager
    def measure(self, name: str):
        started = time.perf_counter()
        try:
            yield
        finally:  # a failed commit still took the time it took
            self.ms[name] = (time.perf_counter() - started) * 1000

    def add_provider_timings(self, timing_ms: Mapping[str, float] | None) -> None:
        """Take the provider's ``timing_ms`` (keys ``preprocess_ms`` / ``vision_ms`` /
        ``telemetry_ms``, present only for a branch that ran)."""
        timing_ms = timing_ms or {}
        for name in ("preprocess", "vision", "telemetry"):
            value = timing_ms.get(f"{name}_ms")
            self.ms[name] = float(value) if value is not None else 0.0
            if value is None:
                self.skipped.add(name)

    def header(self) -> str:
        return format_server_timing(self.ms, self.skipped)


# The timer of the /infer request being handled, if any. Ambient on purpose: the stages
# are timed deep inside functions (``_persist_window``) that the replay route shares and
# that tests call and monkeypatch with fixed signatures, and threading a parameter through
# every one of them would change those signatures. Starlette runs a sync route in one
# worker thread with a copy of the request's context, so a value set by the route is seen
# by everything it calls and by nothing else.
_active: ContextVar[SegmentTimer | None] = ContextVar("segment_timer", default=None)


@contextmanager
def activate(timer: SegmentTimer):
    token = _active.set(timer)
    try:
        yield timer
    finally:
        _active.reset(token)


@contextmanager
def measure(name: str):
    """Time the block under ``name`` if a request timer is active; otherwise do nothing."""
    timer = _active.get()
    if timer is None:
        yield
    else:
        with timer.measure(name):
            yield


def record_provider_timings(timing_ms: Mapping[str, float] | None) -> None:
    timer = _active.get()
    if timer is not None:
        timer.add_provider_timings(timing_ms)
