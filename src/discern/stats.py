"""The statistics, which are the only thing in here that cannot be a little bit wrong.

A tool whose argument is that eval reports produce confident wrong numbers has no licence to
produce one itself. Three choices, and each is the less obvious of two:

**Wilson, not Wald.** Wald is `p +/- 1.96*sqrt(p(1-p)/n)`, which is the one everybody writes
because it fits on a line. It is unusable here for a reason this project cannot overlook: at
p = 0 or p = 1 the standard error is zero, so the interval has **zero width**. Twenty out of
twenty reports `100% +/- 0%`, which is a confident claim of certainty drawn from twenty
samples. Its coverage is also erratic rather than conservative, dipping below 90% for some
n and p well into the hundreds (Brown, Cai and DasGupta, *Statistical Science* 16(2), 2001).

**McNemar, not two proportions, when the runs share their items.** Two prompts are almost
always evaluated over the same eval set, which makes the observations paired. Treating them as
independent discards that structure, and the cost is not theoretical: the required sample size
comes out around twice what the paired calculation asks for. A tool that tells you to collect
340 more runs when 158 would settle it is making the mistake it exists to warn about.

**The exact test when the discordant count is small.** McNemar's `chi2 = (b-c)^2/(b+c)` is an
approximation, and eval runs live exactly where it is worst: a handful of disagreements. Below
a threshold this uses the exact binomial test, and the caller is told which was used.

Nothing here does I/O and nothing here imports the rest of the package.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

#: Two-sided z for a 95% interval. Named rather than inlined so the tests can say what it is.
Z_95 = 1.959963984540054


@dataclass(frozen=True)
class Interval:
    """A proportion and the range it is actually consistent with."""

    point: float
    low: float
    high: float
    n: int

    @property
    def width(self) -> float:
        return self.high - self.low

    def overlaps(self, other: Interval) -> bool:
        return self.low <= other.high and other.low <= self.high


def wilson(successes: int, n: int, z: float = Z_95) -> Interval:
    """A Wilson score interval for a proportion.

    Defined for n = 0, where it returns the whole of [0, 1]: nothing was measured, so every
    proportion is consistent with what was seen. Returning 0 there, or dividing and raising,
    would both be worse than saying the range is everything.
    """
    if n < 0 or successes < 0 or successes > n:
        raise ValueError(f"{successes} successes out of {n} is not a proportion")
    if n == 0:
        return Interval(point=0.0, low=0.0, high=1.0, n=0)

    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    spread = (z / denominator) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return Interval(point=p, low=max(0.0, centre - spread), high=min(1.0, centre + spread), n=n)


def wald(successes: int, n: int, z: float = Z_95) -> Interval:
    """The interval this tool does not use, kept so a test can show why.

    Exported on purpose. The argument for Wilson is not worth making in prose if the
    alternative cannot be run beside it, and `test_stats.py` runs both at 20 out of 20 and
    asserts that this one is the degenerate answer.
    """
    if n == 0:
        return Interval(point=0.0, low=0.0, high=0.0, n=0)
    p = successes / n
    spread = z * math.sqrt(p * (1 - p) / n)
    return Interval(point=p, low=p - spread, high=p + spread, n=n)


# --- comparing two runs -----------------------------------------------------------------


@dataclass(frozen=True)
class Discordance:
    """The 2x2 that a paired comparison actually rests on.

    `both` and `neither` are recorded but carry no information about which run is better: an
    item both runs passed cannot separate them. Only `only_a` and `only_b` can, which is why
    the test is over those two and why a comparison with few of them settles nothing however
    many items were run.
    """

    both: int
    only_a: int
    only_b: int
    neither: int

    @property
    def discordant(self) -> int:
        return self.only_a + self.only_b

    @property
    def n(self) -> int:
        return self.both + self.only_a + self.only_b + self.neither


@dataclass(frozen=True)
class Verdict:
    """What can be said about two runs, and what was used to say it."""

    #: True only when the difference is distinguishable from noise at the chosen level.
    separated: bool
    p_value: float
    method: Literal["mcnemar-exact", "mcnemar-chi2", "two-proportion"]
    paired: bool
    #: Runs of this size each, for the difference observed. None when there is nothing to size.
    needed_per_arm: int | None
    reason: str


#: Where the exact test stops being affordable, not where it stops being right.
#:
#: The exact binomial is valid at every size and is never anti-conservative, so the only
#: reason to approximate is cost. Measured: 1.8 ms at a thousand discordant pairs, 116 ms at
#: five thousand, 5.2 s at twenty thousand, because the tail is a sum of binomial
#: coefficients. Two thousand sits above any eval anybody runs and below where the cost
#: starts to show, so in practice the approximation is never reached.
EXACT_BELOW_DISCORDANT = 2000


def mcnemar(table: Discordance, alpha: float = 0.05) -> tuple[float, str]:
    """Two-sided McNemar over the discordant pairs. Returns the p-value and the method used.

    With no discordant pairs at all there is nothing to test: the two runs agreed on every
    item, so p is 1 by definition rather than by convention.
    """
    b, c = table.only_a, table.only_b
    if b + c == 0:
        return 1.0, "mcnemar-exact"

    if b + c < EXACT_BELOW_DISCORDANT:
        # Exact two-sided binomial on the discordant pairs, against p = 0.5.
        k = min(b, c)
        total = b + c
        tail = sum(math.comb(total, i) for i in range(k + 1)) / (2**total)
        return min(1.0, 2 * tail), "mcnemar-exact"

    # With the continuity correction, and that is not a detail. The uncorrected form
    # `(b-c)^2/(b+c)` approximates a discrete distribution with a continuous one and comes out
    # anti-conservative: at b=30, c=12 it reports p = 0.0055 where the exact test says 0.0079,
    # so it is the likelier of the two to announce a difference. A tool whose whole argument
    # is against calling differences that are not there must not lean that way.
    chi2 = (abs(b - c) - 1) ** 2 / (b + c)
    return _chi2_sf_1df(chi2), "mcnemar-chi2"


def _chi2_sf_1df(x: float) -> float:
    """Upper tail of a chi-square with one degree of freedom.

    One degree of freedom has a closed form through the error function, so this needs no
    special-function library and no dependency: P(X > x) = erfc(sqrt(x/2)).
    """
    if x <= 0:
        return 1.0
    return math.erfc(math.sqrt(x / 2))


def paired_n_needed(p_discordant: float, effect: float, alpha: float = 0.05,
                    power: float = 0.80) -> int | None:
    """Pairs needed to detect this difference, given how often the runs disagree.

    The paired calculation, which is the point. `p_discordant` is the share of items the two
    runs answer differently and `effect` is the difference in pass rate. A pair of runs that
    almost never disagree needs far fewer items than the unpaired formula would demand,
    because agreement carries information too.

    Returns None when the effect is zero: no sample size detects a difference that is not
    there, and returning a large number would read as "collect this many and you will know".
    """
    if effect <= 0 or p_discordant <= 0:
        return None
    z_a = _z_two_sided(alpha)
    z_b = _z_one_sided(1 - power)
    # Standard paired-proportion sizing: the discordant pairs are what the test sees.
    n = ((z_a * math.sqrt(p_discordant) + z_b * math.sqrt(p_discordant - effect**2)) / effect) ** 2
    return math.ceil(n)


def unpaired_n_needed(p1: float, p2: float, alpha: float = 0.05, power: float = 0.80) -> int | None:
    """Per-arm size the *unpaired* test would demand. Reported beside the paired figure.

    Here so the difference between the two is visible in the output rather than asserted in a
    README. It is the number a tool that ignored pairing would tell you to go and collect.
    """
    if p1 == p2:
        return None
    z_a = _z_two_sided(alpha)
    z_b = _z_one_sided(1 - power)
    p_bar = (p1 + p2) / 2
    numerator = (
        z_a * math.sqrt(2 * p_bar * (1 - p_bar))
        + z_b * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    ) ** 2
    return math.ceil(numerator / (p1 - p2) ** 2)


def _z_two_sided(alpha: float) -> float:
    return _inverse_normal(1 - alpha / 2)


def _z_one_sided(beta: float) -> float:
    return _inverse_normal(1 - beta)


def _inverse_normal(p: float) -> float:
    """The standard normal quantile, by bisection on erf.

    A rational approximation would be faster and is what most code uses. This is called a
    handful of times per report, so the slower method that is exact to machine precision is
    free, and it removes a table of magic constants that nobody can check by eye.
    """
    if not 0 < p < 1:
        raise ValueError(f"{p} is not a probability strictly between 0 and 1")
    low, high = -12.0, 12.0
    for _ in range(200):
        mid = (low + high) / 2
        if 0.5 * (1 + math.erf(mid / math.sqrt(2))) < p:
            low = mid
        else:
            high = mid
    return (low + high) / 2
