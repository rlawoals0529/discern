"""The committed vectors still say what this Python says.

Not `git diff`. These are floating-point values from libm, and erf and erfc are not
bit-identical across platforms: erfc(5.0) came out as ...035 here and ...0351 on the CI
runner, which is one unit in the last place and says nothing about anything. A byte
comparison turns that into a failed build and teaches everyone to regenerate the file
without reading the diff, which is the opposite of what the check is for.

So the invariant is stated as what it actually is: the committed answers agree with this
Python to within a tolerance far tighter than the port is tested to, and looser than the
last bit of a double.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

#: Tight enough that any real change to a formula shows, loose enough that a platform's last
#: bit does not. The port itself is checked at 1e-12, so anything this catches is a genuine
#: difference in what the Python computes and not a rounding artefact.
TOLERANCE = 1e-14

COMMITTED = Path("site/vectors.json")


def walk(a, b, path: str, problems: list[str]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                problems.append(f"{path}.{key}: present in only one of them")
                continue
            walk(a[key], b[key], f"{path}.{key}", problems)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            problems.append(f"{path}: {len(a)} entries committed, {len(b)} generated")
            return
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", problems)
    elif isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        if a != b:
            problems.append(f"{path}: {a!r} committed, {b!r} generated")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, int) and isinstance(b, int):
            # Sample sizes are counts. A count is either right or wrong.
            if a != b:
                problems.append(f"{path}: {a} committed, {b} generated")
        else:
            scale = max(abs(a), abs(b), 1e-300)
            if abs(a - b) / scale > TOLERANCE:
                problems.append(f"{path}: {a!r} committed, {b!r} generated")
    elif a != b:
        problems.append(f"{path}: {a!r} committed, {b!r} generated")


def main() -> int:
    if not COMMITTED.exists():
        print(f"{COMMITTED} does not exist. Run: npm run vectors", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        fresh_path = Path(tmp) / "vectors.json"
        # Generate into a scratch directory so a failing check cannot leave the committed
        # file rewritten, which would make the next run pass for the wrong reason.
        subprocess.run(
            [sys.executable, "scripts/export_vectors.py", str(fresh_path)],
            check=True,
        )
        fresh = json.loads(fresh_path.read_text())

    committed = json.loads(COMMITTED.read_text())

    problems: list[str] = []
    walk(committed, fresh, "vectors", problems)

    if problems:
        for p in problems[:20]:
            print(p, file=sys.stderr)
        if len(problems) > 20:
            print(f"... and {len(problems) - 20} more", file=sys.stderr)
        print(
            f"\n{len(problems)} vector(s) no longer match this Python. "
            "If stats.py changed on purpose, run: npm run vectors",
            file=sys.stderr,
        )
        return 1

    print(f"every committed vector agrees with this Python to {TOLERANCE:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
