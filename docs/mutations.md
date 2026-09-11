# Mutations

A test suite nobody has watched fail is not evidence. Each row is a change to the source that
must turn a **named** test red.

The method: back the file up, apply the change, `uv run pytest -q`, restore.

| Mutation | Should fail |
| --- | --- |
| `stats.py`: return `wald(...)` from `wilson` | "twenty out of twenty is not certainty" and the grid |
| `stats.py`: drop the `n == 0` branch in `wilson` | "nothing measured is the whole range rather than zero" |
| `stats.py`: drop the continuity correction from the chi-square | "the approximation does not lean towards announcing a difference" |
| `stats.py`: set `EXACT_BELOW_DISCORDANT = 25` | "every realistic eval gets the exact test" |
| `stats.py`: return a number rather than `None` for a zero effect | "no sample size detects a difference that is not there" |
| `stats.py`: swap `paired_n_needed` for `unpaired_n_needed` | "the paired calculation asks for less than the unpaired one" |
| `compare.py`: assume pairing rather than comparing item ids | "two runs over different items are not paired and it says so" |
| `compare.py`: count an errored item as a failure in the table | "an item one run errored on is not a pair" |
| `outcome.py`: put `errored` in the rate denominator | "the rate denominator excludes errors and skips" |
| `outcome.py`: allow an errored item with no reason | "an error without a reason is refused" |
| `suite.py`: allow a duplicate item id | "a duplicate id is refused because it breaks pairing" |
| `report.py`: print the difference as a winner regardless of the verdict | "a ten point difference over twenty items is not a result" |
| `service/auth.py`: use `==` instead of `compare_digest` | "the token check does not leak the token one byte at a time" |
| `service/auth.py`: allow requests when `DISCERN_TOKEN` is unset | "with no token configured it refuses everything rather than everyone" |
| `service/app.py`: return NaN rather than null for an unpairable comparison | "an unpairable comparison returns null rather than nan" |
| `service/app.py`: compare two suites instead of refusing | "two runs of different suites are refused rather than paired" |
| `service/app.py`: compute a rate in the service instead of calling `compare` | "the service and the library cannot disagree" |
| `service/models.py`: drop the unique constraint on (run_id, item_id) | "a duplicate item id is refused" |

## The one the grid caught and a chosen value could not

The chi-square form of McNemar was implemented uncorrected, which agrees with the textbook
formula and is wrong for this tool's purpose. It is **anti-conservative**: at b=30, c=12 it
reports p = 0.0055 where the exact test says 0.0079, so of the two it is the more likely to
announce a difference.

No hand-picked test case would have found it, because the uncorrected value is a perfectly
good chi-square tail and looks right. It was found by comparing against `statsmodels` across a
grid and noticing the disagreement only appeared above the exact-test threshold. **The lesson
is not "use a second implementation", it is that the cases you choose are the cases you
already thought of.**

## What a property test cannot do here

A property cannot validate a constant. `Z_95` could be 1.64 and every monotonicity property
over intervals would still hold: they would all just be too narrow, consistently. Only a test
pinned to 1.959963985, the number everybody already knows, catches it.
