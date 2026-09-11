"""The command line.

Three verbs. `run` evaluates a suite and writes the result somewhere; `compare` takes two
results and says whether anything can be concluded; `show` prints one on its own.

Results are written as JSON rather than kept in memory between commands, because comparing
two runs from different days is the actual question and a process that exits cannot answer it.

The exit code carries the verdict, so this is usable in CI: 0 when a comparison separated the
runs, 1 when it could not. That is deliberately the opposite way round from a test runner. A
comparison that cannot separate two prompts has not failed, it has answered, and the answer is
"not yet" -- so `--strict` is what turns an unsettled comparison into a non-zero exit for a
pipeline that wants to block on it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .compare import Run, compare
from .outcome import ItemResult, Outcome
from .report import comparison_report, run_report
from .runner import deterministic, run_items
from .suite import load


def _write(run: Run, path: Path) -> None:
    path.write_text(
        json.dumps(
            {"label": run.label, "results": [asdict(r) for r in run.results]},
            indent=2,
            default=str,
        )
        + "\n"
    )


def _read(path: Path) -> Run:
    raw = json.loads(path.read_text())
    return Run(
        label=raw["label"],
        results=[
            ItemResult(
                item_id=r["item_id"],
                outcome=Outcome(r["outcome"]),
                error=r.get("error"),
                duration_ms=r.get("duration_ms"),
            )
            for r in raw["results"]
        ],
    )


def _cmd_run(args: argparse.Namespace) -> int:
    suite = load(args.suite)

    if args.runner != "fake":
        # Refused rather than half-supported. The core deliberately imports no provider, and
        # pretending otherwise here would put a vendor dependency behind a flag nobody read.
        print(
            f"discern: no runner called {args.runner!r}. The core ships only `fake`; "
            "a real one is a callable you pass to `run_items`, or the optional adapter.",
            file=sys.stderr,
        )
        return 2

    # `--fail` names the items the fake should get wrong, so a README example can produce a
    # specific, reproducible comparison rather than a random one.
    failing = set(args.fail or [])
    erroring = {i: "injected failure" for i in (args.error or [])}
    passing = {i.id for i in suite.items} - failing - set(erroring)
    results = run_items(suite.items, deterministic(passing, erroring), suite.label)

    run = Run(label=args.label or suite.label, results=results)
    print(run_report(run))
    if args.out:
        _write(run, Path(args.out))
        print(f"\nwritten to {args.out}")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    result = compare(_read(Path(args.a)), _read(Path(args.b)))
    print(comparison_report(result))
    if args.strict and not result.verdict.separated:
        return 1
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    print(run_report(_read(Path(args.run))))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="discern", description="An eval harness that will not call a difference it cannot see."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="evaluate a suite")
    run_cmd.add_argument("suite")
    run_cmd.add_argument("--runner", default="fake")
    run_cmd.add_argument("--label")
    run_cmd.add_argument("--out")
    run_cmd.add_argument("--fail", nargs="*", help="item ids the fake runner should fail")
    run_cmd.add_argument("--error", nargs="*", help="item ids the fake runner should error on")
    run_cmd.set_defaults(fn=_cmd_run)

    cmp_cmd = sub.add_parser("compare", help="compare two saved runs")
    cmp_cmd.add_argument("a")
    cmp_cmd.add_argument("b")
    cmp_cmd.add_argument(
        "--strict", action="store_true",
        help="exit non-zero when the comparison cannot separate the runs",
    )
    cmp_cmd.set_defaults(fn=_cmd_compare)

    show_cmd = sub.add_parser("show", help="print one saved run")
    show_cmd.add_argument("run")
    show_cmd.set_defaults(fn=_cmd_show)

    args = parser.parse_args(argv)
    try:
        return int(args.fn(args))
    except (FileNotFoundError, ValueError, TypeError) as exc:
        # The message is the whole point of catching these: a traceback for a malformed
        # suite file sends you to read this module instead of the file you got wrong.
        print(f"discern: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
