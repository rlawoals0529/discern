"""One bearer token, checked on every service request.

The service is deliberately single-user: adding a user table, sessions and roles would create
an authentication system this tool does not need. The token therefore stays small, fail-closed,
constant-time, and rate-limited as a backstop against repeated guessing.
"""

from __future__ import annotations

import hmac
import os
import time
from collections import OrderedDict, deque

from fastapi import Header, HTTPException, Request

_AUTH_WINDOW_SECONDS = 300
_AUTH_FAILURE_LIMIT = 30
_AUTH_BUCKET_CAP = 2048
_auth_failures: OrderedDict[str, deque[float]] = OrderedDict()


def expected_token() -> str | None:
    return os.environ.get("DISCERN_TOKEN")


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _prune(bucket: deque[float], now: float) -> None:
    while bucket and now - bucket[0] >= _AUTH_WINDOW_SECONDS:
        bucket.popleft()


def _too_many_failures(request: Request) -> bool:
    key = _client_key(request)
    bucket = _auth_failures.get(key)
    if not bucket:
        return False
    now = time.monotonic()
    _prune(bucket, now)
    if not bucket:
        _auth_failures.pop(key, None)
        return False
    _auth_failures.move_to_end(key)
    return len(bucket) >= _AUTH_FAILURE_LIMIT


def _record_failure(request: Request) -> None:
    key = _client_key(request)
    now = time.monotonic()
    bucket = _auth_failures.setdefault(key, deque())
    _prune(bucket, now)
    bucket.append(now)
    _auth_failures.move_to_end(key)

    # A public service can see many source addresses. Keep the limiter itself bounded so an
    # attacker cannot turn protection into a memory-growth primitive.
    while len(_auth_failures) > _AUTH_BUCKET_CAP:
        _auth_failures.popitem(last=False)


def _clear_failures(request: Request) -> None:
    _auth_failures.pop(_client_key(request), None)


def require_token(request: Request, authorization: str = Header(default="")) -> None:
    """Reject missing or incorrect credentials and fail closed when unconfigured."""
    expected = expected_token()
    if not expected:
        raise HTTPException(
            503,
            "DISCERN_TOKEN is not set, so this service cannot authenticate anyone and is "
            "refusing everything. Set it and restart.",
        )

    if _too_many_failures(request):
        raise HTTPException(
            429,
            "Too many failed authentication attempts. Try again later.",
            headers={"Retry-After": str(_AUTH_WINDOW_SECONDS)},
        )

    scheme, _, presented = authorization.partition(" ")
    if scheme.lower() != "bearer" or not presented:
        _record_failure(request)
        raise HTTPException(401, "Send an Authorization header: `Bearer <token>`.")

    if not hmac.compare_digest(presented, expected):
        _record_failure(request)
        raise HTTPException(401, "That token is not the one this service was started with.")

    _clear_failures(request)
