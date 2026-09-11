"""The statistics, checked against something that is not this repository.

An implementation tested against its own output is tested against nothing. These go two ways,
and the two catch different things:

- **Hand-computable cases**, where the answer can be worked out on paper. These catch a wrong
  formula. `mcnemar` with b=3, c=0 must be 0.25, because the exact two-sided test is twice the
  probability of three heads: 2 * (1/2)^3.
- **A grid against statsmodels**, an independent implementation. This catches the edges a
  handful of chosen cases miss: n=1, k=0, k=n, and the awkward middle.

Neither alone is enough. A published value cannot tell you the function breaks at n=1, and a
grid agreeing with another library cannot tell you both are computing the wrong thing.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from statsmodels.stats.contingency_tables import mcnemar as sm_mcnemar
from statsmodels.stats.proportion import proportion_confint

from discern.stats import (
    Discordance,
    mcnemar,
    paired_n_needed,
    unpaired_n_needed,
    wald,
    wilson,
)


class TestWilson:
    def test_it_agrees_with_an_independent_implementation_across_a_grid(self):
        # statsmodels is a dev dependency for exactly this. Two implementations agreeing to
        # machine precision is a much stronger statement than one implementation agreeing
        # with the value it produced yesterday.
        for n in [1, 2, 5, 20, 47, 100, 997]:
            for k in {0, 1, n // 3, n // 2, max(n - 1, 0), n}:
                if k > n:
                    continue
                mine = wilson(k, n)
                low, high = proportion_confint(k, n, alpha=0.05, method="wilson")
                assert mine.low == pytest.approx(low, abs=1e-12), f"low differs at {k}/{n}"
                assert mine.high == pytest.approx(high, abs=1e-12), f"high differs at {k}/{n}"

    def test_twenty_out_of_twenty_is_not_certainty(self):
        # The case this project exists for. A perfect score over twenty items is consistent
        # with a true rate in the mid eighties, and any report that says otherwise is making
        # a claim its sample cannot support.
        interval = wilson(20, 20)
        assert interval.point == 1.0
        assert interval.low < 0.85, "a perfect run of twenty must not exclude a rate below 85%"
        assert interval.width > 0.1, "twenty for twenty is not a measurement of certainty"

    def test_nothing_measured_is_the_whole_range_rather_than_zero(self):
        # Zero successes out of zero items is not a 0% pass rate. It is no information, and
        # the interval that says so is [0, 1].
        interval = wilson(0, 0)
        assert (interval.low, interval.high) == (0.0, 1.0)

    def test_the_interval_never_leaves_the_unit_range(self):
        # Wald does leave it, which is the other half of why this one is used.
        for n in range(1, 60):
            for k in range(n + 1):
                interval = wilson(k, n)
                assert 0.0 <= interval.low <= interval.high <= 1.0, f"{k}/{n} left [0,1]"

    def test_more_evidence_narrows_it(self):
        # The property that makes an interval worth printing: the same rate measured over
        # more items says more.
        widths = [wilson(n // 2, n).width for n in [10, 40, 160, 640]]
        assert widths == sorted(widths, reverse=True), "more samples must not widen the interval"

    def test_a_proportion_that_is_not_one_is_refused(self):
        for successes, n in [(5, 2), (-1, 10), (3, -1)]:
            with pytest.raises(ValueError):
                wilson(successes, n)


class TestWaldIsTheAlternativeThisRejects:
    def test_wald_reports_certainty_from_twenty_samples(self):
        # Kept runnable rather than described, because the argument for Wilson is only worth
        # making if the thing it replaced can be put beside it. This is the number a report
        # using the textbook interval would print: 100% plus or minus nothing.
        assert wald(20, 20).width == 0.0
        assert wilson(20, 20).width > 0.1

    def test_wald_leaves_the_unit_range_where_wilson_does_not(self):
        # 1 out of 20 is an ordinary eval result, and the textbook interval puts part of it
        # below zero, which is not a pass rate anything can have.
        assert wald(1, 20).low < 0.0
        assert wilson(1, 20).low >= 0.0


class TestMcNemar:
    def test_three_disagreements_all_one_way_is_a_quarter(self):
        # Hand-computable, and the reason it is here: the exact two-sided test on three
        # discordant pairs that all favour one run is 2 * (1/2)^3 = 0.25. A formula error
        # shows up immediately against a number that can be worked out on paper.
        p, method = mcnemar(Discordance(both=10, only_a=3, only_b=0, neither=7))
        assert p == pytest.approx(0.25)
        assert method == "mcnemar-exact"

    def test_it_agrees_with_an_independent_implementation(self):
        for b, c in [(3, 0), (10, 4), (1, 1), (7, 2), (12, 11), (30, 12), (40, 39), (1200, 1100)]:
            mine, _ = mcnemar(Discordance(both=50, only_a=b, only_b=c, neither=50))
            theirs = sm_mcnemar(np.array([[50, b], [c, 50]]), exact=(b + c < 2000)).pvalue
            assert mine == pytest.approx(theirs, abs=1e-12), f"differs at b={b}, c={c}"

    def test_two_runs_that_never_disagreed_settle_nothing(self):
        # No discordant pairs means the runs answered every item the same way. There is
        # nothing to separate them, and p = 1 by definition rather than by convention.
        p, _ = mcnemar(Discordance(both=100, only_a=0, only_b=0, neither=0))
        assert p == 1.0

    def test_every_realistic_eval_gets_the_exact_test(self):
        # The approximation is a cost saving, not a better answer, so the threshold sits
        # above anything anybody actually runs. Which test was used is returned rather than
        # hidden, because it is part of the answer.
        _, few = mcnemar(Discordance(both=10, only_a=4, only_b=1, neither=10))
        _, many = mcnemar(Discordance(both=10, only_a=40, only_b=20, neither=10))
        _, enormous = mcnemar(Discordance(both=0, only_a=1200, only_b=1100, neither=0))
        assert few == "mcnemar-exact"
        assert many == "mcnemar-exact", "sixty disagreements is not where an approximation is needed"
        assert enormous == "mcnemar-chi2"

    def test_the_approximation_does_not_lean_towards_announcing_a_difference(self):
        # Found by cross-checking against statsmodels, which applies the continuity
        # correction by default. The uncorrected form `(b-c)^2/(b+c)` reports p = 0.0055
        # at b=30, c=12 where the exact test says 0.0079: it is the likelier of the two to
        # call a difference, which is the one direction this tool must not err in.
        from discern.stats import _chi2_sf_1df

        b, c = 30, 12
        uncorrected = _chi2_sf_1df((b - c) ** 2 / (b + c))
        exact, _ = mcnemar(Discordance(both=0, only_a=b, only_b=c, neither=0))
        assert uncorrected < exact, "the uncorrected form is anti-conservative, which is why it is not used"
        assert exact == pytest.approx(0.00791590, abs=1e-6)

    def test_only_the_disagreements_count(self):
        # The heart of the paired test, and the thing that surprises people: adding a
        # thousand items that both runs passed changes nothing about which is better.
        small, _ = mcnemar(Discordance(both=5, only_a=6, only_b=1, neither=5))
        huge, _ = mcnemar(Discordance(both=5000, only_a=6, only_b=1, neither=5000))
        assert small == huge


class TestSampleSize:
    def test_the_paired_calculation_asks_for_less_than_the_unpaired_one(self):
        # The finding the whole tool is built around. Two prompts evaluated on the same items
        # are paired, and a tool that ignores that tells you to collect roughly twice the
        # runs you actually need before you can call the result.
        paired = paired_n_needed(p_discordant=0.20, effect=0.06)
        unpaired = unpaired_n_needed(0.81, 0.87)
        assert paired is not None and unpaired is not None
        assert paired < unpaired, "ignoring pairing must not ask for fewer samples"

    def test_runs_that_rarely_disagree_need_fewer_items(self):
        # Agreement carries information. Two prompts that differ on one item in twenty settle
        # their difference sooner than two that differ on one in three.
        rarely = paired_n_needed(p_discordant=0.05, effect=0.03)
        often = paired_n_needed(p_discordant=0.40, effect=0.03)
        assert rarely is not None and often is not None
        assert rarely < often

    def test_no_sample_size_detects_a_difference_that_is_not_there(self):
        # Returning a large number here would read as "collect this many and you will know",
        # which is false. There is no n that resolves a zero effect.
        assert paired_n_needed(p_discordant=0.2, effect=0.0) is None
        assert unpaired_n_needed(0.8, 0.8) is None

    def test_a_smaller_difference_needs_more_evidence(self):
        sizes = [paired_n_needed(0.3, e) for e in [0.20, 0.10, 0.05, 0.02]]
        assert all(s is not None for s in sizes)
        assert sizes == sorted(sizes), "a subtler difference must not be cheaper to detect"

    def test_the_normal_quantile_is_right_where_it_is_checkable(self):
        # Used by both sizing functions. 1.959963985 is the two-sided 95% z, and it is the
        # one number in this file that everybody already knows.
        from discern.stats import Z_95, _inverse_normal

        assert _inverse_normal(0.975) == pytest.approx(Z_95, abs=1e-9)
        assert _inverse_normal(0.5) == pytest.approx(0.0, abs=1e-9)
        assert _inverse_normal(0.8413447460685429) == pytest.approx(1.0, abs=1e-7)

    def test_the_chi_square_tail_matches_the_error_function_it_is_built_from(self):
        from discern.stats import _chi2_sf_1df

        # A chi-square with one degree of freedom at 3.841459 is the 5% point, which is the
        # number every textbook prints.
        assert _chi2_sf_1df(3.841458820694124) == pytest.approx(0.05, abs=1e-9)
        assert _chi2_sf_1df(0.0) == 1.0
        assert _chi2_sf_1df(1.0) == pytest.approx(math.erfc(math.sqrt(0.5)))
