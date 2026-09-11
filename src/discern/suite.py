"""Reading a suite off disk.

YAML because an eval suite is written by hand and read by a person, and because a list of
prompts in JSON is a wall of escaped quotes.

Every failure here names the file and the item. A suite that fails to load with "KeyError:
'id'" sends you to read the loader instead of the file you got wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .runner import Item


@dataclass(frozen=True)
class Suite:
    label: str
    items: list[Item]


def load(path: str | Path) -> Suite:
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text())
    except FileNotFoundError:
        raise FileNotFoundError(f"{p} does not exist") from None
    except yaml.YAMLError as exc:
        raise ValueError(f"{p} is not valid YAML: {exc}") from None

    # A wrong type and a wrong value are different mistakes and send you to different
    # places: the first means the file is not a suite at all, the second that it is one and
    # is missing something.
    if not isinstance(raw, dict):
        raise TypeError(f"{p} should be a mapping with `label` and `items`")

    items_raw = raw.get("items")
    if not isinstance(items_raw, list):
        raise TypeError(f"{p} has an `items` that is not a list")
    if not items_raw:
        raise ValueError(f"{p} has no items, so there is nothing to evaluate")

    items: list[Item] = []
    seen: set[str] = set()
    for index, entry in enumerate(items_raw):
        if not isinstance(entry, dict):
            raise TypeError(f"{p} item {index} is not a mapping")
        if "id" not in entry or "prompt" not in entry:
            raise ValueError(f"{p} item {index} needs at least `id` and `prompt`")
        item_id = str(entry["id"])
        # Duplicate ids would silently destroy the pairing: two runs are matched by id, so
        # an id that appears twice makes one of the two invisible to the comparison.
        if item_id in seen:
            raise ValueError(f"{p} uses the id {item_id!r} twice, which breaks pairing")
        seen.add(item_id)
        items.append(
            Item(id=item_id, prompt=str(entry["prompt"]), expected=entry.get("expected"))
        )

    return Suite(label=str(raw.get("label") or p.stem), items=items)
