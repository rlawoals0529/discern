"""One token, checked on every request.

A stored run contains the prompts that were evaluated and, through the error strings, often
what the model said about them. Anything that can reach the port can read all of it, so the
port needs a door.

**One token and not a user table**, and that is a deliberate stopping point. Users, roles and
sessions would be a mechanism invented for a problem this tool does not have: there is one
person here and the thing being protected is a read of their own history. Adding the mechanism
anyway is how a small tool acquires an authentication system nobody asked for and nobody
audits.

The comparison is constant time. A token check that returns early on the first wrong byte
leaks the token one byte at a time to anyone patient, and `==` on strings does return early.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def expected_token() -> str | None:
    return os.environ.get("DISCERN_TOKEN")


def require_token(authorization: str = Header(default="")) -> None:
    """Reject anything without the bearer token.

    With no token configured the service refuses every request rather than allowing every
    request. An unset variable is a deployment that has not been finished, and the safe
    reading of that is closed rather than open.
    """
    expected = expected_token()
    if not expected:
        raise HTTPException(
            503,
            "DISCERN_TOKEN is not set, so this service cannot authenticate anyone and is "
            "refusing everything. Set it and restart.",
        )

    scheme, _, presented = authorization.partition(" ")
    if scheme.lower() != "bearer" or not presented:
        raise HTTPException(401, "Send an Authorization header: `Bearer <token>`.")

    if not hmac.compare_digest(presented, expected):
        raise HTTPException(401, "That token is not the one this service was started with.")
