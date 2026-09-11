"""Which comparison the data supports, decided from the data."""

from __future__ import annotations

import math

from discern.compare import Run, compare
from discern.outcome import ItemResult, Outcome


def run(label: str, passes: set[str], fails: set[str] = frozenset(),
        errors: set[str] = frozenset()) -> Run:
    results = [ItemResult(i, Outcome.PASSED) for i in sorted(passes)]
    results += [ItemResult(i, Outcome.FAILED) for i in sorted(fails)]
    results += [ItemResult(i, Outcome.ERRORED, error="boom") for i in sorted(errors)]
    return Run(label, results)


def test_two_runs_over_the_same_items_are_paired_without_being_told():
    # The caller is never asked. Pairing is a fact about the items, and a flag would let it
    # be set wrongly.
    a = run("a", passes={"1", "2", "3"}, fails={"4"})
    b = run("b", passes={"1", "2", "4"}, fails={"3"})
    result = compare(a, b)
    assert result.verdict.paired is True
    assert result.verdict.method.startswith("mcnemar")


def test_two_runs_over_different_items_are_not_paired_and_it_says_so():
    # The weaker comparison, and the weakness is invisible unless it is printed. No p-value
    # is invented for samples that were never comparable.
    a = run("a", passes={"1", "2"}, fails={"3"})
    b = run("b", passes={"7", "8"}, fails={"9"})
    result = compare(a, b)
    assert result.verdict.paired is False
    assert math.isnan(result.verdict.p_value), "a test over incomparable runs must not be reported"
    assert "cannot be paired" in result.verdict.reason


def test_a_ten_point_difference_over_twenty_items_is_not_a_result():
    # The case the tool exists for, and the one every dashboard renders as a win.
    a = run("a", passes={f"i{n}" for n in range(16)}, fails={f"i{n}" for n in range(16, 20)})
    b = run("b", passes={f"i{n}" for n in range(18)}, fails={f"i{n}" for n in range(18, 20)})
    result = compare(a, b)
    assert result.verdict.separated is False
    assert result.verdict.needed_per_arm is not None
    assert result.verdict.needed_per_arm > 20, "it must ask for more than was already run"


def test_a_difference_large_enough_is_called():
    # The tool has to be able to say yes, or it is not measuring, it is just refusing.
    items = {f"i{n}" for n in range(40)}
    a = run("a", passes=set(), fails=items)
    b = run("b", passes=items)
    result = compare(a, b)
    assert result.verdict.separated is True
    assert result.verdict.p_value < 0.05


def test_only_the_items_they_disagreed_on_can_separate_them():
    # Adding two hundred items both runs pass changes the rates and changes nothing about
    # which run is better. This is what pairing means and it surprises people.
    shared_pass = {f"same{n}" for n in range(200)}
    a = run("a", passes={"x"} | shared_pass, fails={"y"})
    b = run("b", passes={"y"} | shared_pass, fails={"x"})
    small = compare(run("a", passes={"x"}, fails={"y"}), run("b", passes={"y"}, fails={"x"}))
    large = compare(a, b)
    assert large.verdict.p_value == small.verdict.p_value


def test_an_item_one_run_errored_on_is_not_a_pair():
    # A network failure must not become evidence about which prompt is better. The item is
    # dropped from the comparison rather than counted as a loss for the run that errored.
    a = run("a", passes={"1", "2"}, errors={"3"})
    b = run("b", passes={"1", "2"}, fails={"3"})
    result = compare(a, b)
    assert result.table is not None
    assert result.table.n == 2, "the errored item must not be in the paired table"
    assert result.table.discordant == 0


def test_partially_overlapping_runs_compare_the_overlap_and_say_so():
    # Not all or nothing. The shared items are a real paired comparison, and the rest are
    # named as excluded rather than quietly dropped.
    a = run("a", passes={"1", "2", "3"})
    b = run("b", passes={"2", "3", "9"})
    result = compare(a, b)
    assert result.verdict.paired is True
    assert result.table is not None and result.table.n == 2
    assert "only one run" in result.verdict.reason


def test_two_identical_runs_cannot_be_separated_by_any_sample_size():
    # Returning a number here would read as "collect this many and you will know", which is
    # false when there is nothing to find.
    items = {f"i{n}" for n in range(30)}
    a = run("a", passes=items)
    b = run("b", passes=items)
    result = compare(a, b)
    assert result.verdict.separated is False
    assert result.verdict.needed_per_arm is None
