"""The HTTP surface over stored runs.

Four endpoints, and they answer the questions the CLI cannot: what has been run, what did one
run say, and can two of them be told apart. Every comparison goes through `compare.compare`,
so the service cannot reach a different verdict from the command line. There is no second
implementation of the statistics here and there must never be one.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..compare import Run as RunData
from ..compare import compare
from ..outcome import ItemResult, Outcome
from .auth import require_token
from .db import get_db
from .models import Result, Run

app = FastAPI(
    title="discern",
    version="0.1.0",
    description="Stored eval runs, and whether two of them can be told apart.",
)


class ResultIn(BaseModel):
    item_id: str
    outcome: Outcome
    error: str | None = None
    duration_ms: int | None = None


class RunIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    suite: str = Field(min_length=1, max_length=200)
    results: list[ResultIn] = Field(min_length=1)


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
        # Refused here as well as in the suite loader, because a run can arrive over HTTP
        # without ever passing through one. A duplicate id makes an item invisible to the
        # paired comparison, silently.
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
def list_runs(suite: str | None = None, limit: int = 50, db: Session = Depends(get_db)) -> dict:
    stmt = select(Run).order_by(Run.created_at.desc()).limit(min(limit, 200))
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
        # Said rather than attempted. Two different suites may share item ids by coincidence,
        # and pairing on those would be a comparison of unrelated things wearing the shape of
        # a real one.
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
        # None rather than NaN, which is not valid JSON and which some clients turn into 0.
        "p_value": None if verdict.p_value != verdict.p_value else verdict.p_value,
        "method": verdict.method,
        "paired": verdict.paired,
        "needed_per_arm": verdict.needed_per_arm,
        "reason": verdict.reason,
        "discordant": result.table.discordant if result.table else None,
    }
