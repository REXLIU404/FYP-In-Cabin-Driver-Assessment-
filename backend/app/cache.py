"""In-memory Output Cache: latest risk_update per session for fast polling."""
from .schemas import RiskUpdate

_latest: dict[str, RiskUpdate] = {}


def set_latest(session_id: str, ru: RiskUpdate) -> None:
    _latest[session_id] = ru


def get_latest(session_id: str) -> RiskUpdate | None:
    return _latest.get(session_id)


def clear(session_id: str) -> None:
    _latest.pop(session_id, None)
