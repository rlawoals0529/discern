"""The service, including the two things that are only true over HTTP."""

from __future__ import annotations

import pytest


def run_body(label: str, passes: int, fails: int, suite: str = "arithmetic", offset: int = 0):
    results = [{"item_id": f"i{n}", "outcome": "passed"} for n in range(passes)]
    results += [{"item_id": f"i{passes + n}", "outcome": "failed"} for n in range(fails)]
    if offset:
        for r in results:
            r["item_id"] = f"z{offset}-" + r["item_id"]
    return {"label": label, "suite": suite, "results": results}


class TestAuth:
    def test_without_a_token_nothing_is_readable(self, client):
        # A stored run holds the prompts that were evaluated. Anything that can reach the
        # port can read them unless something stops it.
        for method, path in [("get", "/runs"), ("get", "/runs/1"), ("get", "/compare/1/2")]:
            assert getattr(client, method)(path).status_code == 401, f"{path} was readable"

    def test_a_wrong_token_is_refused(self, client):
        r = client.get("/runs", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401

    def test_the_scheme_has_to_be_bearer(self, client, token):
        r = client.get("/runs", headers={"Authorization": token})
        assert r.status_code == 401, "a bare token with no scheme must not be accepted"

    def test_with_no_token_configured_it_refuses_everything_rather_than_everyone(
        self, client, monkeypatch
    ):
        # An unset variable is a deployment somebody has not finished. The safe reading is
        # closed, not open, and 503 says which of the two happened rather than 401 implying
        # the caller got it wrong.
        monkeypatch.delenv("DISCERN_TOKEN", raising=False)
        assert client.get("/runs").status_code == 503

    def test_the_token_check_does_not_leak_the_token_one_byte_at_a_time(self):
        # `==` on strings returns on the first differing byte, which is measurable over
        # enough requests. Pinned because the constant-time call looks like a stylistic
        # choice and is not.
        import inspect

        from discern.service import auth

        source = inspect.getsource(auth.require_token)
        assert "compare_digest" in source, "the token comparison must be constant time"


class TestRuns:
    def test_a_run_is_stored_and_comes_back_with_its_interval(self, client, auth):
        created = client.post("/runs", json=run_body("prompt-a", 16, 4), headers=auth)
        assert created.status_code == 201
        body = created.json()
        # Never a bare rate, over HTTP or anywhere else. A client that receives a bare number
        # renders a bare number.
        assert body["rate"] == pytest.approx(0.8)
        assert body["low"] < 0.8 < body["high"]

    def test_a_duplicate_item_id_is_refused(self, client, auth):
        # Refused here as well as in the suite loader, because a run can arrive over HTTP
        # having never passed through one.
        body = run_body("a", 2, 0)
        body["results"].append({"item_id": "i0", "outcome": "failed"})
        assert client.post("/runs", json=body, headers=auth).status_code == 422

    def test_errored_items_stay_out_of_the_rate_and_are_counted(self, client, auth):
        body = run_body("a", 2, 0)
        body["results"].append({"item_id": "x", "outcome": "errored", "error": "timeout"})
        created = client.post("/runs", json=body, headers=auth).json()
        assert created["answered"] == 2
        assert created["errored"] == 1
        assert created["is_partial"] is True
        assert created["rate"] == 1.0, "the rate is over answered items"

    def test_a_run_that_does_not_exist_says_so(self, client, auth):
        assert client.get("/runs/9999", headers=auth).status_code == 404

    def test_history_comes_back_newest_first(self, client, auth):
        for label in ["one", "two", "three"]:
            client.post("/runs", json=run_body(label, 5, 5), headers=auth)
        labels = [r["label"] for r in client.get("/runs", headers=auth).json()["runs"]]
        assert labels[0] == "three", "the most recent run is the one you came to look at"


class TestCompareOverHttp:
    def test_the_service_and_the_library_cannot_disagree(self, client, auth, db):
        # There is one implementation of the statistics and the service calls it. This is
        # what stops a second one appearing here later.
        from discern.compare import Run as RunData
        from discern.compare import compare
        from discern.outcome import ItemResult, Outcome

        a = client.post("/runs", json=run_body("a", 16, 4), headers=auth).json()
        b = client.post("/runs", json=run_body("b", 18, 2), headers=auth).json()
        over_http = client.get(f"/compare/{a['id']}/{b['id']}", headers=auth).json()

        def as_data(label, passes, fails):
            results = [ItemResult(f"i{n}", Outcome.PASSED) for n in range(passes)]
            results += [ItemResult(f"i{passes + n}", Outcome.FAILED) for n in range(fails)]
            return RunData(label, results)

        direct = compare(as_data("a", 16, 4), as_data("b", 18, 2)).verdict
        assert over_http["p_value"] == pytest.approx(direct.p_value)
        assert over_http["needed_per_arm"] == direct.needed_per_arm
        assert over_http["separated"] is direct.separated

    def test_two_runs_of_different_suites_are_refused_rather_than_paired(self, client, auth):
        # Two suites can share item ids by coincidence. Pairing on those would be a
        # comparison of unrelated things wearing the shape of a real one.
        a = client.post("/runs", json=run_body("a", 5, 5, suite="arithmetic"), headers=auth).json()
        b = client.post("/runs", json=run_body("b", 5, 5, suite="reasoning"), headers=auth).json()
        r = client.get(f"/compare/{a['id']}/{b['id']}", headers=auth)
        assert r.status_code == 422
        assert "different questions" in r.json()["detail"]

    def test_an_unpairable_comparison_returns_null_rather_than_nan(self, client, auth):
        # NaN is not valid JSON, and the clients that accept it anyway tend to render it as
        # zero, which would read as a p-value of zero: the most significant result possible.
        a = client.post("/runs", json=run_body("a", 5, 5, offset=1), headers=auth).json()
        b = client.post("/runs", json=run_body("b", 5, 5, offset=2), headers=auth).json()
        body = client.get(f"/compare/{a['id']}/{b['id']}", headers=auth).json()
        assert body["paired"] is False
        assert body["p_value"] is None
