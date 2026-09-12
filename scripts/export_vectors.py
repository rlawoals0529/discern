"""Answers from the Python, for the TypeScript port to be judged against.

The port in site/stats.ts is a second implementation, and a second implementation drifts.
Testing it against itself would prove only that it is self-consistent, which is not the
property anybody wants from it - so this runs the real functions over a spread of inputs
and writes what they said. CI regenerates this file and fails if it has moved, so the
vectors cannot quietly become whatever the port happens to produce.

The inputs are chosen to include the cases where the two languages part company: n = 0,
0 and 100 per cent where Wald degenerates, discordant counts small enough to be exact and
large enough to overflow a double, and effects small enough that the sizing blows up.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

# Imported from src/, not from whatever is installed.
#
# `uv run` resolves `discern` to the built package in the environment, which is a copy
# made at sync time. Editing stats.py and regenerating then produces the OLD answers, and the
# drift check compares the committed vectors against a build nobody is looking at. The point
# of this file is to capture what the working tree computes, so it says which tree.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from discern.stats import (
    Discordance,
    mcnemar,
    paired_n_needed,
    unpaired_n_needed,
    wald,
    wilson,
)

PROPORTIONS = [
    (0, 0), (0, 1), (1, 1), (0, 20), (20, 20), (1, 20), (16, 20), (18, 20),
    (1, 3), (50, 100), (99, 100), (1, 1000), (999, 1000), (500, 1000),
]

TABLES = [
    (0, 0, 0, 0), (18, 0, 2, 0), (10, 5, 5, 10), (10, 0, 10, 10),
    (100, 30, 12, 100), (0, 1, 0, 0), (0, 0, 1, 0), (500, 1, 1, 500),
    (0, 40, 10, 0), (2000, 60, 40, 2000),
]

SIZING = [
    (0.10, 0.05), (0.20, 0.10), (0.50, 0.25), (0.05, 0.01),
    (0.30, 0.0), (0.0, 0.10), (0.99, 0.5),
]

UNPAIRED = [(0.8, 0.9), (0.5, 0.5), (0.01, 0.02), (0.5, 0.99), (0.9, 0.8)]

# erf is the one thing the port cannot transcribe: JavaScript has no erf, so it reimplements
# one. These are the values it has to reproduce.
ERF_AT = [0.0, 0.1, 0.5, 1.0, 1.5, 1.9, 2.0, 2.1, 3.0, 4.0, 5.0, 5.9, -0.5, -2.5]


def interval(i) -> dict:
    return {"point": i.point, "low": i.low, "high": i.high, "n": i.n}


vectors = {
    "z95": __import__("discern.stats", fromlist=["Z_95"]).Z_95,
    "wilson": [
        {"successes": s, "n": n, "expected": interval(wilson(s, n))} for s, n in PROPORTIONS
    ],
    "wald": [{"successes": s, "n": n, "expected": interval(wald(s, n))} for s, n in PROPORTIONS],
    "mcnemar": [],
    "paired_n_needed": [
        {"p_discordant": p, "effect": e, "expected": paired_n_needed(p, e)} for p, e in SIZING
    ],
    "unpaired_n_needed": [
        {"p1": a, "p2": b, "expected": unpaired_n_needed(a, b)} for a, b in UNPAIRED
    ],
    "erf": [{"x": x, "expected": math.erf(x)} for x in ERF_AT],
    "erfc": [{"x": x, "expected": math.erfc(x)} for x in ERF_AT],
}

for both, only_a, only_b, neither in TABLES:
    p, method = mcnemar(Discordance(both=both, only_a=only_a, only_b=only_b, neither=neither))
    vectors["mcnemar"].append(
        {
            "table": {"both": both, "onlyA": only_a, "onlyB": only_b, "neither": neither},
            "expected": {"p": p, "method": method},
        }
    )

# An argument so the drift check can generate into a scratch directory: a check that
# rewrote the file it is checking would make the next run pass for the wrong reason.
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("site/vectors.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(vectors, indent=2) + "\n")

counted = sum(len(v) for v in vectors.values() if isinstance(v, list))
print(f"{counted} vectors from the Python into {out}")
