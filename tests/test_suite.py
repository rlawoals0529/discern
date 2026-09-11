"""Loading a suite, and the one mistake that would silently destroy a comparison."""

from __future__ import annotations

import pytest

from discern.suite import load


def write(tmp_path, text: str):
    p = tmp_path / "suite.yaml"
    p.write_text(text)
    return p


def test_a_duplicate_id_is_refused_because_it_breaks_pairing():
    # The important one. Two runs are matched by item id, so an id used twice makes one of
    # the two invisible to the paired comparison, and nothing anywhere else would notice.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.yaml"
        p.write_text("label: x\nitems:\n  - {id: a, prompt: one}\n  - {id: a, prompt: two}\n")
        with pytest.raises(ValueError, match="twice"):
            load(p)


def test_the_example_suite_loads(tmp_path):
    # The file the README tells people to run. A README whose first command fails is worse
    # than a README with no commands in it.
    suite = load("examples/arithmetic.yaml")
    assert suite.label == "arithmetic"
    assert len(suite.items) == 20
    assert len({i.id for i in suite.items}) == 20, "the example must not have duplicate ids"


def test_a_missing_file_says_which_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="nope.yaml"):
        load(tmp_path / "nope.yaml")


def test_an_empty_suite_is_refused_rather_than_reported_as_zero_percent(tmp_path):
    # Zero items is not a 0% pass rate, and a harness that runs nothing and prints a rate
    # is the failure this whole project is about.
    with pytest.raises(ValueError, match="no items"):
        load(write(tmp_path, "label: x\nitems: []\n"))


def test_an_item_missing_its_prompt_names_the_item(tmp_path):
    # The error has to send you to the line you got wrong, not to the loader.
    with pytest.raises(ValueError, match="item 1"):
        load(write(tmp_path, "label: x\nitems:\n  - {id: a, prompt: p}\n  - {id: b}\n"))


def test_something_that_is_not_a_suite_is_a_type_error(tmp_path):
    with pytest.raises(TypeError):
        load(write(tmp_path, "- just\n- a\n- list\n"))
