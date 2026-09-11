"""Comparing two runs, and working out from the data which comparison is available.

Two prompts are almost always evaluated over the same eval set. That makes the observations
**paired**, and pairing is not a detail: it is most of the information. If both runs pass the
same eighteen items and disagree on two, the interesting number is two, and a test that treats
the runs as independent samples of size twenty throws that away.

The cost is measurable. The unpaired calculation asks for roughly twice as many items to reach
the same confidence. A tool that tells you to go and collect 585 runs when 434 would settle it
is making the mistake it exists to warn about, in the act of warning you.

So this does not ask the caller whether the runs are paired. **It compares the item ids.** If
they match it says so and uses McNemar; if they do not it says that too, and reports the
weaker unpaired comparison with the reason attached rather than silently.
"""

from __future__ import annotations

from dataclasses import dataclass

from .outcome import ItemResult, Outcome, Tally
from .stats import (
    Discordance,
    Interval,
    Verdict,
    mcnemar,
    paired_n_needed,
    unpaired_n_needed,
    wilson,
)


@dataclass(frozen=True)
class Run:
    """One evaluation of one configuration over a set of items."""

    label: str
    results: list[ItemResult]

    @property
    def tally(self) -> Tally:
        return Tally.of(self.results)

    @property
    def rate(self) -> Interval:
        t = self.tally
        return wilson(t.passed, t.answered)

    def by_item(self) -> dict[str, ItemResult]:
        return {r.item_id: r for r in self.results}


@dataclass(frozen=True)
class Comparison:
    a: Run
    b: Run
    verdict: Verdict
    #: Only populated for a paired comparison. The four cells the paired test rests on.
    table: Discordance | None


def compare(a: Run, b: Run, alpha: float = 0.05) -> Comparison:
    """Compare two runs, using whichever test the data actually supports."""
    shared = _shared_answered_items(a, b)
    a_items, b_items = a.by_item(), b.by_item()

    # Pairing is decided by the items, not by the caller. Two runs over the same set are
    # paired whether or not anybody said so, and two runs over different sets are not,
    # however much somebody wants them to be.
    a_answered = {i for i, r in a_items.items() if r.outcome in (Outcome.PASSED, Outcome.FAILED)}
    b_answered = {i for i, r in b_items.items() if r.outcome in (Outcome.PASSED, Outcome.FAILED)}
    fully_paired = bool(a_answered) and a_answered == b_answered

    if not shared:
        return Comparison(a, b, _unpaired(a, b, alpha, why=_why_unpaired(a_answered, b_answered)), None)

    table = _tabulate(a_items, b_items, shared)
    p_value, method = mcnemar(table, alpha=alpha)

    effect = abs(a.rate.point - b.rate.point)
    p_discordant = table.discordant / table.n if table.n else 0.0
    needed = paired_n_needed(p_discordant, effect) if p_discordant else None

    if fully_paired:
        why = (
            f"Both runs answered the same {table.n} items, so the comparison is paired and "
            f"only the {table.discordant} they disagreed on can separate them."
        )
    else:
        why = (
            f"{len(shared)} items were answered by both runs and are compared as pairs. "
            f"The rest were answered by only one run and cannot take part in the comparison."
        )

    return Comparison(
        a,
        b,
        Verdict(
            separated=p_value < alpha,
            p_value=p_value,
            method=method,
            paired=True,
            needed_per_arm=needed,
            reason=why,
        ),
        table,
    )


def _shared_answered_items(a: Run, b: Run) -> set[str]:
    """Items both runs actually answered.

    An item one run errored on is not a pair. Counting it would put a network failure into
    the evidence about which prompt is better.
    """
    answered = {Outcome.PASSED, Outcome.FAILED}
    return {i for i, r in a.by_item().items() if r.outcome in answered} & {
        i for i, r in b.by_item().items() if r.outcome in answered
    }


def _tabulate(a_items: dict[str, ItemResult], b_items: dict[str, ItemResult],
              shared: set[str]) -> Discordance:
    both = only_a = only_b = neither = 0
    for item in shared:
        a_pass = a_items[item].outcome is Outcome.PASSED
        b_pass = b_items[item].outcome is Outcome.PASSED
        if a_pass and b_pass:
            both += 1
        elif a_pass:
            only_a += 1
        elif b_pass:
            only_b += 1
        else:
            neither += 1
    return Discordance(both=both, only_a=only_a, only_b=only_b, neither=neither)


def _unpaired(a: Run, b: Run, alpha: float, why: str) -> Verdict:
    """The weaker comparison, used only when there is nothing to pair.

    No p-value is reported. Two runs with no items in common can have their rates put side by
    side and that is all; inventing a test over samples that were never comparable would be
    the confident wrong number this tool is against. What is reported instead is the size
    each arm would need for the comparison to be worth making.
    """
    needed = unpaired_n_needed(a.rate.point, b.rate.point, alpha=alpha)
    return Verdict(
        separated=False,
        p_value=float("nan"),
        method="two-proportion",
        paired=False,
        needed_per_arm=needed,
        reason=why,
    )


def _why_unpaired(a_answered: set[str], b_answered: set[str]) -> str:
    if not a_answered or not b_answered:
        return "One of the runs answered nothing, so there is nothing to compare."
    return (
        "The two runs share no answered items, so they cannot be paired. Rates are shown "
        "side by side and no test is reported: a comparison over different items is a "
        "different question."
    )
