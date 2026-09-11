"""Three states, and the rate that can honestly be drawn from them."""

from __future__ import annotations

import pytest

from discern.outcome import ItemResult, Outcome, Tally


def test_an_error_is_not_a_failure():
    # The distinction the whole type exists for. A timeout and a wrong answer both leave the
    # item unpassed, and only one of them says anything about the thing under test.
    tally = Tally.of([
        ItemResult("a", Outcome.PASSED),
        ItemResult("b", Outcome.FAILED),
        ItemResult("c", Outcome.ERRORED, error="rate limited"),
    ])
    assert (tally.passed, tally.failed, tally.errored) == (1, 1, 1)


def test_the_rate_denominator_excludes_errors_and_skips():
    # A denominator that includes a network failure is a rate that moves when the network
    # does. Two passes out of two answered is 100%, whatever else went wrong around it.
    tally = Tally.of([
        ItemResult("a", Outcome.PASSED),
        ItemResult("b", Outcome.PASSED),
        ItemResult("c", Outcome.ERRORED, error="timeout"),
        ItemResult("d", Outcome.SKIPPED),
    ])
    assert tally.answered == 2
    assert tally.total == 4
    assert tally.is_partial is True


def test_a_complete_run_is_not_partial():
    # The flag has to be off sometimes, or it is decoration. A caveat that is always shown
    # is a caveat nobody reads.
    tally = Tally.of([ItemResult("a", Outcome.PASSED), ItemResult("b", Outcome.FAILED)])
    assert tally.is_partial is False


def test_an_error_without_a_reason_is_refused():
    # An errored item whose cause is unrecorded cannot be acted on, and it is the shape a
    # harness bug arrives in. Refused at construction rather than rendered as "unknown".
    with pytest.raises(ValueError, match="without saying why"):
        ItemResult("a", Outcome.ERRORED)


def test_a_passing_item_cannot_carry_an_error():
    # The other direction, which is how a copy-paste in a runner starts reporting error
    # strings on successful items.
    with pytest.raises(ValueError, match="carries an error"):
        ItemResult("a", Outcome.PASSED, error="but also this")


def test_nothing_at_all_tallies_to_zero_rather_than_throwing():
    tally = Tally.of([])
    assert (tally.answered, tally.total, tally.is_partial) == (0, 0, False)
