"""Rendering, which is where every refusal becomes visible or does not."""

from __future__ import annotations

from discern.compare import Run, compare
from discern.outcome import ItemResult, Outcome
from discern.report import comparison_report, run_report
from discern.stats import wilson


def run(label: str, passes: set[str] = frozenset(), fails: set[str] = frozenset(),
        errors: set[str] = frozenset()) -> Run:
    results = [ItemResult(i, Outcome.PASSED) for i in sorted(passes)]
    results += [ItemResult(i, Outcome.FAILED) for i in sorted(fails)]
    results += [ItemResult(i, Outcome.ERRORED, error="timeout") for i in sorted(errors)]
    return Run(label, results)


def test_a_rate_is_never_printed_without_its_interval():
    # The claim this tool makes is made in the formatting, so it is tested in the formatting.
    text = run_report(run("a", passes={"1", "2", "3"}, fails={"4"}))
    assert "75.0%" in text
    assert "[" in text and "to" in text, "a rate was printed with no interval beside it"


def test_a_ten_point_difference_over_twenty_items_is_not_a_result():
    # Named in docs/mutations.md. Making the report print a winner regardless of the verdict
    # must turn this red.
    a = run("a", passes={f"i{n}" for n in range(16)}, fails={f"i{n}" for n in range(16, 20)})
    b = run("b", passes={f"i{n}" for n in range(18)}, fails={f"i{n}" for n in range(18, 20)})
    text = comparison_report(compare(a, b))
    assert "indistinguishable" in text
    assert "is better" not in text, "a difference the test could not separate was called a win"
    assert "items each would settle" in text, "refusing without saying what would settle it is not advice"


def test_a_real_difference_is_called():
    # The report has to be able to say yes, or it is not measuring anything.
    items = {f"i{n}" for n in range(40)}
    text = comparison_report(compare(run("a", fails=items), run("b", passes=items)))
    assert "is better" in text
    assert "indistinguishable" not in text


def test_errors_are_printed_beside_the_rate_and_not_inside_it():
    text = run_report(run("a", passes={"1", "2"}, errors={"3"}))
    assert "100.0%" in text, "the rate is over answered items"
    assert "1 errored" in text and "2 of 3 answered" in text
    assert "timeout" in text, "the reason has to survive to the report"


def test_a_complete_run_says_nothing_about_partiality():
    # A caveat that is always on is a caveat nobody reads.
    text = run_report(run("a", passes={"1"}, fails={"2"}))
    assert "errored" not in text and "answered" not in text


def test_incomparable_runs_get_no_p_value_at_all():
    # Printing a test statistic for runs that share no items would dress up a comparison
    # that was never available.
    text = comparison_report(compare(run("a", passes={"1"}), run("b", passes={"9"})))
    assert "not comparable" in text
    assert "p = " not in text


def test_a_run_with_nothing_answered_says_so_rather_than_showing_zero():
    text = run_report(run("a", errors={"1", "2"}))
    assert "no answered items" in text
    assert "0.0%" not in text, "nothing answered is not a zero percent pass rate"


def test_the_interval_helper_renders_n_zero_without_dividing():
    assert "no answered items" in run_report(Run("empty", []))
    assert wilson(0, 0).high == 1.0
