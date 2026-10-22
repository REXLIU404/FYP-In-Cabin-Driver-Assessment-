"""Read access to fault events, and the global handlers that make the failures the
``/infer`` route cannot see observable.

The route records everything that happens inside it. Two kinds of failure never
reach it, and are recorded here instead:

* ``RequestValidationError`` - FastAPI rejects the body (or the ``X-Attempt-Index``
  header) before ``infer_frame`` runs, so this handler is the ONLY place a schema 422
  on ``/infer`` is observable. ``request_id`` is dug out of ``exc.body``.
* a stray ``Exception`` - raised outside the route's own code (for instance while
  FastAPI validates the response).

Both handlers return exactly the response FastAPI / Starlette would have produced,
so status codes and bodies are unchanged; they only add a fault row. They record
``POST /api/sessions/{id}/infer`` and nothing else - the replay ``/windows`` route
is not part of the live failure model.
"""
import inspect
import re
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import faults
from ..db import get_db
from ..schemas import FaultEventOut

router = APIRouter(prefix="/api", tags=["faults"])

# Every response this backend produces carries this header (see ``main.BackendMarkerMiddleware``).
# It lives here because the one response a middleware cannot reach - the plain-text 500 below -
# must add it by hand, and ``main`` already imports this module. The front end reads it to tell
# an answer of this backend from one a proxy or gateway invented when the backend is not running.
BACKEND_HEADER = "X-DRA-Backend"
BACKEND_HEADER_VALUE = "1"

_INFER_PATH = re.compile(r"^/api/sessions/(?P<session_id>[^/]+)/infer$")


@router.get("/faults", response_model=list[FaultEventOut])
def list_faults(session_id: Optional[str] = Query(None), limit: int = Query(500, ge=1, le=1000),
                db: Session = Depends(get_db)):
    """Fault events, oldest first (``occurred_at``, then ``id``). They are kept after the
    session is deleted, so a deleted session's id still returns its faults."""
    return faults.list_fault_events(db, session_id=session_id, limit=limit)


def _infer_session_id(request: Request) -> Optional[str]:
    """The session id if this request is ``POST /api/sessions/{id}/infer``, else None."""
    if request.method != "POST":
        return None
    match = _INFER_PATH.match(request.url.path)
    if not match:
        return None
    return request.path_params.get("session_id") or match.group("session_id")


def _record_outside_route(request: Request, *, session_id: str, request_id: Optional[str],
                          attempt_index: Optional[int], info: faults.FaultClass) -> None:
    """Record with the same database and sink the route would have used, resolved
    through the app's dependency overrides (so a test's temporary ones apply)."""
    overrides = request.app.dependency_overrides
    produced = overrides.get(get_db, get_db)()
    db, close = (next(produced), produced.close) if inspect.isgenerator(produced) else (produced, produced.close)
    try:
        faults.record_fault(db, session_id=session_id, request_id=request_id,
                            attempt_index=attempt_index, origin=info.origin,
                            error_category=info.error_category, http_status=info.http_status,
                            retryable=info.retryable, detail=info.detail,
                            sink=overrides.get(faults.get_fault_sink, faults.get_fault_sink)())
    finally:
        close()


async def on_request_validation_error(request: Request, exc: RequestValidationError):
    session_id = _infer_session_id(request)
    if session_id is not None:
        try:
            info = faults.FaultClass(
                origin=faults.ORIGIN_REQUEST_VALIDATION, error_category=faults.CATEGORY_INPUT_VALIDATION,
                http_status=422, retryable=faults.RETRYABLE[faults.CATEGORY_INPUT_VALIDATION],
                detail=faults.describe_validation_errors(exc.errors()))
            await run_in_threadpool(
                _record_outside_route, request, session_id=session_id,
                request_id=faults.request_id_from_body(exc.body),
                attempt_index=faults.parse_attempt_header(request.headers.get("x-attempt-index")), info=info)
        except Exception:  # recording must never change the 422 the client gets
            faults.logger.exception("could not record a request-validation fault")
    return await request_validation_exception_handler(request, exc)


def on_unhandled_exception(request: Request, exc: Exception):
    session_id = _infer_session_id(request)
    if session_id is not None and not getattr(request.state, "fault_recorded", False):
        try:
            context = getattr(request.state, "fault_context", None) or {}
            _record_outside_route(
                request, session_id=session_id, request_id=context.get("request_id"),
                attempt_index=context.get("attempt_index",
                                          faults.parse_attempt_header(request.headers.get("x-attempt-index"))),
                info=faults.classify_exception(exc))
        except Exception:
            faults.logger.exception("could not record an unhandled-exception fault")
    # Starlette's own default body; it re-raises the exception after sending it. The header is
    # added HERE: ServerErrorMiddleware sits outside every user middleware, so the marker
    # middleware never sees this response.
    return PlainTextResponse("Internal Server Error", status_code=500,
                             headers={BACKEND_HEADER: BACKEND_HEADER_VALUE})


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, on_request_validation_error)
    app.add_exception_handler(Exception, on_unhandled_exception)
