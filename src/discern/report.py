"""Rendering, which is where the refusals become visible.

Everything this tool believes ends up here as a formatting decision:

- a rate is never printed without its interval
- a difference is never printed as a winner unless the test separated it
- errors and skips are printed beside the rate, never inside it
- the sample size that would settle the question is printed when the question is open,
  because "not significant" without a number is advice nobody can act on

The output is plain text on purpose. A dashboard is where a six-point difference becomes a
green arrow, and the green arrow is the thing being argued with.
"""

from __future__ import annotations

from .compare import Comparison, Run
from .outcome import Outcome
from .stats import Interval


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def rate_line(label: str, interval: Interval) -> str:
    """One run's rate, always with its interval.

    There is no code path here that prints a bare percentage, and that is deliberate: the
    formatting is where the claim is made, so the claim is made once.
    """
    if interval.n == 0:
        return f"{label:<16} no answered items, so no rate"
    return (
        f"{label:<16} {_pct(interval.point):>6}  "
        f"[{_pct(interval.low)} to {_pct(interval.high)}]   n={interval.n}"
    )


def run_report(run: Run) -> str:
    """One run: the rate, the interval, and what is not in the denominator."""
    tally = run.tally
    lines = [rate_line(run.label, run.rate)]

    if tally.is_partial:
        # Beside the rate, never folded into it. An errored item is not a failed one, and a
        # denominator that includes it moves whenever the network does.
        parts = []
        if tally.errored:
            parts.append(f"{tally.errored} errored")
        if tally.skipped:
            parts.append(f"{tally.skipped} never ran")
        lines.append(
            f"{'':<16} {', '.join(parts)}, excluded from the rate above "
            f"({tally.answered} of {tally.total} answered)"
        )

    errors = [r for r in run.results if r.outcome is Outcome.ERRORED]
    if errors:
        seen: dict[str, int] = {}
        for e in errors:
            seen[e.error or "unknown"] = seen.get(e.error or "unknown", 0) + 1
        for reason, count in sorted(seen.items(), key=lambda kv: -kv[1]):
            lines.append(f"{'':<16}   {count}x {reason}")

    return "\n".join(lines)


def comparison_report(comparison: Comparison) -> str:
    """Two runs, and whether anything can be said about the difference between them."""
    a, b = comparison.a, comparison.b
    verdict = comparison.verdict
    lines = [run_report(a), run_report(b), ""]

    difference = b.rate.point - a.rate.point
    lines.append(f"difference       {difference * 100:+.1f} points")

    if comparison.table is not None:
        t = comparison.table
        lines.append(
            f"{'':<16} {t.discordant} of {t.n} items separated them "
            f"({t.only_a} only {a.label}, {t.only_b} only {b.label})"
        )

    lines.append("")

    if not verdict.paired:
        # No p-value, on purpose. Two runs over different items are not a comparison, and
        # printing a test statistic here would dress one up as if it were.
        lines.append("not comparable   " + verdict.reason)
        if verdict.needed_per_arm:
            lines.append(
                f"{'':<16} a fresh run over one shared set of "
                f"{verdict.needed_per_arm} items would answer it"
            )
        return "\n".join(lines)

    if verdict.separated:
        better = b.label if difference > 0 else a.label
        lines.append(f"separated        {better} is better, p = {verdict.p_value:.4f} ({verdict.method})")
    else:
        # The whole point of the tool. The difference is reported, and the claim is not made.
        lines.append(
            f"indistinguishable from noise at this sample size, "
            f"p = {verdict.p_value:.4f} ({verdict.method})"
        )
        if verdict.needed_per_arm:
            lines.append(
                f"{'':<16} about {verdict.needed_per_arm} items each would settle a "
                f"difference this size"
            )
        else:
            lines.append(
                f"{'':<16} the two runs agreed on every item, so no sample size separates them"
            )

    lines.append(f"{'':<16} {verdict.reason}")
    return "\n".join(lines)
