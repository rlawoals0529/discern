from __future__ import annotations


def test_repeated_bad_tokens_are_throttled(client, monkeypatch):
    from discern.service import auth

    auth._auth_failures.clear()
    monkeypatch.setattr(auth, "_AUTH_FAILURE_LIMIT", 2)

    headers = {"Authorization": "Bearer wrong"}
    assert client.get("/runs", headers=headers).status_code == 401
    assert client.get("/runs", headers=headers).status_code == 401

    limited = client.get("/runs", headers=headers)
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == str(auth._AUTH_WINDOW_SECONDS)

    auth._auth_failures.clear()


def test_successful_authentication_clears_the_failure_bucket(client, auth, monkeypatch):
    from discern.service import auth as auth_module

    auth_module._auth_failures.clear()
    monkeypatch.setattr(auth_module, "_AUTH_FAILURE_LIMIT", 2)

    assert client.get("/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/runs", headers=auth).status_code == 200
    assert client.get("/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401

    auth_module._auth_failures.clear()


def test_auth_limiter_has_a_hard_bucket_cap():
    from discern.service import auth

    assert auth._AUTH_BUCKET_CAP > 0
    assert auth._AUTH_BUCKET_CAP < 100_000
