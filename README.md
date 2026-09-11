# discern

An eval harness that will not call a difference it cannot see.

```
prompt-a          80.0%  [58.4% to 91.9%]   n=20
prompt-b          90.0%  [69.9% to 97.2%]   n=20

difference       +10.0 points
                 2 of 20 items separated them (0 only prompt-a, 2 only prompt-b)

indistinguishable from noise at this sample size, p = 0.5000 (mcnemar-exact)
                 about 77 items each would settle a difference this size
```

Ten points looks like a result. Two items separated the runs, which settles nothing, and the
report says so and says what would settle it.

## What it will not report

- **It never prints a bare percentage.** Every rate carries its interval.
- **It never calls a winner the test cannot support.** It says how many items would.
- **It never counts an error as a failure.** A timeout and a wrong answer mean opposite
  things, so the pass rate is over answered items and the rest is printed beside it.
- **It never compares two runs over different items without saying so**, and it reports no
  p-value for them at all, because a comparison over different items is a different question.

## Why Wilson and McNemar

A tool whose argument is that eval reports produce confident wrong numbers has no licence to
produce one. Each of these is the less obvious of two, and each is checked in `tests/` against
an implementation that is not this one.

**Wilson, not Wald.** Wald is `p ± 1.96·√(p(1-p)/n)`, the one everybody writes because it fits
on a line. At p̂ = 0 or 1 its standard error is zero, so it has **zero width**: twenty out of
twenty reports `100% ± 0%`, a claim of certainty drawn from twenty samples. It also runs
outside [0,1] on ordinary results, and its coverage oscillates rather than converging, dipping
under 90% for some n and p well into the hundreds (Brown, Cai & DasGupta, *Statistical
Science* 16(2), 2001). `stats.wald` is exported so a test can run both side by side.

**McNemar, not two proportions.** Two prompts are almost always evaluated over the same items,
which makes the observations **paired**, and pairing is most of the information: if both runs
pass the same eighteen items and differ on two, the interesting number is two. The unpaired
test discards that and asks for roughly twice the sample to reach the same confidence, so a
tool that ignores it tells you to collect 585 runs when 434 would do. **This does not ask
whether the runs are paired. It compares the item ids.**

**The exact test, not the approximation.** `χ² = (b-c)²/(b+c)` approximates a discrete
distribution with a continuous one and comes out **anti-conservative**: at b=30, c=12 it
reports p = 0.0055 where the exact test says 0.0079, making it the likelier of the two to
announce a difference. That is the one direction this tool must not lean. The exact binomial
is used everywhere it is affordable, which measurement puts at any eval anybody actually runs,
and the continuity-corrected form is the fallback above that. The report names which was used.

## Run it

```bash
uv sync
uv run discern run examples/arithmetic.yaml --label prompt-a --fail add-3 div-2 --out a.json
uv run discern run examples/arithmetic.yaml --label prompt-b --fail add-3 --out b.json
uv run discern compare a.json b.json
```

`--strict` exits non-zero when a comparison cannot separate the runs, for a pipeline that
wants to block on it. Without it the exit code is 0, because a comparison that settles nothing
has answered the question rather than failed.

## Bring your own runner

A runner is any callable taking an item and returning a bool. **Nothing in the core imports a
provider SDK**, and that is not squeamishness about dependencies: a harness whose tests need
an API key either holds a secret in CI or skips the tests that matter, and it is then in no
position to lecture anybody about evidence. The whole suite runs with no key and no network.

```python
from discern.compare import Run, compare
from discern.runner import Item, run_items

def my_runner(item: Item) -> bool:
    return call_whatever_you_like(item.prompt) == item.expected

results = run_items(items, my_runner, label="prompt-a")
```

Raising is how a runner says it could not get an answer. That becomes an errored item, not a
failed one.

## Keeping the history

A single run is a command line concern. "Did this get better since last week" is not, and it
is the question people actually have, so runs can be stored.

```bash
docker compose up -d --wait
uv run alembic upgrade head
DISCERN_TOKEN=$(openssl rand -hex 16) uv run uvicorn discern.service.app:app --port 8210
```

```
POST /runs                 store a run
GET  /runs?suite=...       history, newest first
GET  /runs/{id}            one run, with its items
GET  /compare/{a}/{b}      the same verdict the CLI gives
```

**The three outcomes are stored, not a pass rate.** Storing the rate would make the errored
and skipped items unrecoverable, and every honest thing this tool says depends on still being
able to tell those apart. The rate is derived on the way out.

**Every endpoint needs a bearer token**, because a stored run holds the prompts that were
evaluated and often, through the error strings, what the model said about them. With
`DISCERN_TOKEN` unset the service refuses everything with a 503 rather than allowing
everything: an unset variable is a deployment somebody did not finish, and the safe reading of
that is closed. It is one token and not a user table, because there is one person here and
roles would be a mechanism invented for a problem this does not have.

**Two runs of different suites are refused rather than paired.** Two suites can share item ids
by coincidence, and pairing on those is a comparison of unrelated things wearing the shape of
a real one.

## Tests

```bash
docker compose up -d --wait
uv run alembic upgrade head
uv run pytest
```

Sixty-one tests. The service ones run against **real Postgres**, because what they are testing
is a schema: a unique constraint, timezone-aware timestamps, and a migration that has to be
right. An in-memory stand-in exercises none of those, so testing the fake would prove nothing
about the thing that ships. `alembic check` runs as its own CI job, because "the migration has
drifted from the models" and "a test failed" are different problems.

The statistics are checked two ways, because neither alone is enough. Hand-computable cases
catch a wrong formula: exact McNemar on three disagreements all one way must be 2·(1/2)³ =
0.25, which anybody can do on paper. A grid against `statsmodels` catches the edges a handful
of chosen cases miss, at n=1, k=0 and k=n. A published value cannot tell you the function
breaks at n=1, and two libraries agreeing cannot tell you both are wrong.

The continuity-correction bug above was found by that grid, not by writing the code.

`docs/mutations.md` lists the changes that must each turn a named test red.

## Stack

Python 3.11+ · FastAPI · SQLAlchemy 2 · PostgreSQL 17 · Alembic · pytest · ruff · uv

No runtime dependency on any model provider, enforced by `scripts/check_no_provider.py`.

MIT © James Kim
