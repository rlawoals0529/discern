"""What happened to one item, in three states rather than two.

Almost every eval harness reports a pass rate, which means it has divided the world into
passed and everything else. Everything else contains two things that mean opposite things:

    FAILED   the model answered, and the answer was wrong
    ERRORED  the harness did not get an answer at all

A timeout, a rate limit, a malformed response and a bug in the grader are all ERRORED. Rolling
them into the failures makes a broken harness look like a bad model, and the number moves in
the direction that makes you change the prompt.

    SKIPPED  the item was never attempted

is the third, and it exists so that "we ran 20 of the 100" cannot render as 80 failures.

**The pass rate is over answered items only**, and the count of everything else travels beside
it. A denominator that quietly includes errors is a rate that drifts whenever the network does.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Outcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    #: The harness never got an answer. Not a failure of the thing under test.
    ERRORED = "errored"
    #: Never attempted.
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ItemResult:
    """One item, once."""

    item_id: str
    outcome: Outcome
    #: Present only for ERRORED, and it is why. A rate limit and a grader crash are not the
    #: same problem, and the report cannot tell them apart without this.
    error: str | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        if self.outcome is Outcome.ERRORED and not self.error:
            raise ValueError(f"{self.item_id} errored without saying why, which is unusable")
        if self.outcome is not Outcome.ERRORED and self.error:
            raise ValueError(f"{self.item_id} is {self.outcome.value} and carries an error")


@dataclass(frozen=True)
class Tally:
    """The four counts, and the rate that can honestly be drawn from them."""

    passed: int
    failed: int
    errored: int
    skipped: int

    @classmethod
    def of(cls, results: list[ItemResult]) -> Tally:
        counts = {o: 0 for o in Outcome}
        for r in results:
            counts[r.outcome] += 1
        return cls(
            passed=counts[Outcome.PASSED],
            failed=counts[Outcome.FAILED],
            errored=counts[Outcome.ERRORED],
            skipped=counts[Outcome.SKIPPED],
        )

    @property
    def answered(self) -> int:
        """The denominator. Errors and skips are not evidence about the thing under test."""
        return self.passed + self.failed

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errored + self.skipped

    @property
    def is_partial(self) -> bool:
        """True when the rate is drawn from less than everything that was asked for."""
        return self.errored > 0 or self.skipped > 0
