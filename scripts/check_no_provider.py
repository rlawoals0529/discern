#!/usr/bin/env python
"""Refuse a model provider in the core, because the claim is that there is not one.

"Runs with no API key" is a claim that decays the moment it lives only in a README, since
adding an import is one line and nobody reads the diff of a lockfile. This makes it a check.

It greps for the import, not for intent, because intent is not greppable. A false positive
costs one line explaining why a name is allowed. A false negative means the front page is
wrong and the test suite quietly needs a secret.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

#: Not a blocklist of every provider, which would be a list that goes stale. These are the
#: clients whose presence would mean the core had grown a network dependency on somebody
#: else's service, which is the thing being refused.
REFUSED = {"openai", "anthropic", "cohere", "google.generativeai", "litellm", "requests", "httpx"}

#: The one place a provider is allowed, because it is opt-in and not imported by the core.
ALLOWED_UNDER = Path("src/discern/adapters")


def imported_names(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def main() -> int:
    files = sorted(Path("src/discern").rglob("*.py"))
    if not files:
        # A run that checked nothing must not report success. An empty tree is the shape
        # this fails silently-clean in, and a green tick over zero files is worse than no
        # check at all.
        print("check_no_provider: found no files under src/discern, so nothing was checked")
        return 2

    problems: list[str] = []
    checked = 0
    for f in files:
        if ALLOWED_UNDER in f.parents:
            continue
        checked += 1
        for name in imported_names(ast.parse(f.read_text())) & REFUSED:
            problems.append(f"{f}: imports {name}")

    if problems:
        print("check_no_provider: the core imports a provider or an HTTP client:")
        for p in problems:
            print(f"  {p}")
        print(
            "\nIf this one is genuinely fine, move it under src/discern/adapters/ or add it "
            "here with a reason. Do not widen the list: the list is the claim."
        )
        return 1

    print(f"check_no_provider: {checked} files, no provider and no HTTP client in the core")
    return 0


if __name__ == "__main__":
    sys.exit(main())
