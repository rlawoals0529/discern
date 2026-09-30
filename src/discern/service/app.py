"""The HTTP surface over stored runs.

Four endpoints, and they answer the questions the CLI cannot: what has been run, what did one
run say, and can two of them be told apart. Every comparison goes through `compare.compare`,
so the service cannot reach a different verdict from the command line. There is no second
implementation of the statistics here and there must never be one.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..compare import Run as RunData
from ..compare import compare
from ..outcome import ItemResult, Outcome
from .auth import require_token
from .db import get_db
from .models import Result, Run

MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_RESULTS_PER_RUN = 10_000

app = FastAPI(
    title="discern",
    version="0.1.0",
    description="Stored eval runs, and whether two of them can be told apart.",
)

_SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


@app.middleware("http")
async def security_boundary(request: Request, call_next):
    raw_length = request.headers.get("content-length")
    if raw_length:
        try:
            if int(raw_length) > MAX_REQUEST_BYTES:
                return JSONResponse({"detail": "Request body is too large."}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length header."}, status_code=400)

    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        response.headers[name] = value
    response.headers["Cache-Control"] = "no-store"
    return response


class ResultIn(BaseModel):
    item_id: str = Field(min_length=1, max_length=500)
    outcome: Outcome
    error: str | None = Field(default=None, max_length=20_000)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)


class RunIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    suite: str = Field(min_length=1, max_length=200)
    results: list[ResultIn] = Field(min_length=1, max_length=MAX_RESULTS_PER_RUN)


def _to_data(run: Run) -> RunData:
    return RunData(
        label=run.label,
        results=[
            ItemResult(
                item_id=r.item_id,
                outcome=Outcome(r.outcome),
                error=r.error,
                duration_ms=r.duration_ms,
            )
            for r in run.results
        ],
    )


def _rate(run: RunData) -> dict:
    """A rate is never returned on its own, over HTTP or anywhere else.

    The interval and the counts that are not in the denominator travel with it, because a
    client that receives a bare number will render a bare number.
    """
    interval, tally = run.rate, run.tally
    return {
        "passed": tally.passed,
        "failed": tally.failed,
        "errored": tally.errored,
        "skipped": tally.skipped,
        "answered": tally.answered,
        "rate": interval.point if interval.n else None,
        "low": interval.low,
        "high": interval.high,
        "is_partial": tally.is_partial,
    }


@app.post("/runs", status_code=201, dependencies=[Depends(require_token)])
def create_run(body: RunIn, db: Session = Depends(get_db)) -> dict:
    seen = {r.item_id for r in body.results}
    if len(seen) != len(body.results):
        raise HTTPException(422, "An item id appears twice in this run, which breaks pairing.")

    run = Run(label=body.label, suite=body.suite)
    run.results = [
        Result(
            item_id=r.item_id,
            outcome=r.outcome.value,
            error=r.error,
            duration_ms=r.duration_ms,
        )
        for r in body.results
    ]
    db.add(run)
    db.commit()
    return {"id": run.id, "label": run.label, "suite": run.suite, **_rate(_to_data(run))}


@app.get("/runs", dependencies=[Depends(require_token)])
def list_runs(
    suite: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(Run).order_by(Run.created_at.desc()).limit(limit)
    if suite:
        stmt = stmt.where(Run.suite == suite)
    runs = db.scalars(stmt).all()
    return {
        "runs": [
            {
                "id": r.id,
                "label": r.label,
                "suite": r.suite,
                "created_at": r.created_at.isoformat(),
                **_rate(_to_data(r)),
            }
            for r in runs
        ]
    }


@app.get("/runs/{run_id}", dependencies=[Depends(require_token)])
def get_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, f"There is no run {run_id}.")
    data = _to_data(run)
    return {
        "id": run.id,
        "label": run.label,
        "suite": run.suite,
        **_rate(data),
        "results": [
            {"item_id": r.item_id, "outcome": r.outcome, "error": r.error} for r in run.results
        ],
    }


@app.get("/compare/{a_id}/{b_id}", dependencies=[Depends(require_token)])
def compare_runs(a_id: int, b_id: int, db: Session = Depends(get_db)) -> dict:
    a, b = db.get(Run, a_id), db.get(Run, b_id)
    missing = [i for i, r in ((a_id, a), (b_id, b)) if r is None]
    if missing:
        raise HTTPException(404, f"No run with id {' or '.join(map(str, missing))}.")

    if a.suite != b.suite:
        raise HTTPException(
            422,
            f"Run {a_id} is over suite {a.suite!r} and run {b_id} is over {b.suite!r}. "
            "Those are different questions, so they are not compared.",
        )

    result = compare(_to_data(a), _to_data(b))
    verdict = result.verdict
    return {
        "a": {"id": a.id, "label": a.label, **_rate(_to_data(a))},
        "b": {"id": b.id, "label": b.label, **_rate(_to_data(b))},
        "separated": verdict.separated,
        "p_value": None if verdict.p_value != verdict.p_value else verdict.p_value,
        "method": verdict.method,
        "paired": verdict.paired,
        "needed_per_arm": verdict.needed_per_arm,
        "reason": verdict.reason,
        "discordant": result.table.discordant if result.table else None,
    }
