"""How an item gets answered, which this package deliberately does not know how to do.

A runner is any callable that takes an item and returns whether it passed. That is the whole
interface, and it is the whole interface on purpose.

**Nothing in the core imports a provider SDK.** The alternative was to build this around one
vendor's client, which would have meant the test suite needed an API key, so CI would either
hold a secret or skip the tests that matter. A harness that cannot run its own tests in CI is
not in a position to lecture anybody about evidence.

The cost is that `discern` on its own evaluates nothing: you bring the runner. One adapter for
a real provider lives in `discern.adapters`, behind an extra, so the dependency is opt-in and
the core stays testable with no network at all.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .outcome import ItemResult, Outcome


@dataclass(frozen=True)
class Item:
    """One thing to evaluate. `expected` is whatever the runner wants to compare against."""

    id: str
    prompt: str
    expected: str | None = None


class Runner(Protocol):
    """Answer one item.

    Returning a bool keeps graders out of this package. Raising is how a runner reports that
    it could not get an answer, and that is caught here and recorded as ERRORED rather than
    as a failure: see `outcome.py` for why those must not be the same thing.
    """

    def __call__(self, item: Item) -> bool: ...


def run_items(items: list[Item], runner: Runner, label: str) -> list[ItemResult]:
    """Run every item, turning an exception into an errored result rather than a stack trace.

    One item raising must not end the run. A harness that stops at the first timeout reports
    a partial result as though it were the whole one, and the pass rate it prints is drawn
    from whichever items happened to come first.
    """
    results: list[ItemResult] = []
    for item in items:
        started = time.perf_counter()
        try:
            passed = runner(item)
        except Exception as exc:  # noqa: BLE001 - any failure to answer is an errored item
            # The class name is kept because "TimeoutError" and "KeyError" send you to
            # different places, and a bare message often says neither.
            results.append(
                ItemResult(
                    item.id,
                    Outcome.ERRORED,
                    error=f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            continue
        results.append(
            ItemResult(
                item.id,
                Outcome.PASSED if passed else Outcome.FAILED,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        )
    return results


def deterministic(passing: set[str], erroring: dict[str, str] | None = None) -> Callable[[Item], bool]:
    """A runner with no model behind it, for tests and for `--runner fake`.

    Deterministic on purpose. A fake that returned random results would make every test of
    this harness flaky, which is a poor advertisement for a tool about measurement noise.
    """
    erroring = erroring or {}

    def run(item: Item) -> bool:
        if item.id in erroring:
            raise RuntimeError(erroring[item.id])
        return item.id in passing

    return run
