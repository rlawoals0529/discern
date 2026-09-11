"""Engine and session. One place, so the tests and the service cannot drift apart."""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

#: Port 5434 rather than 5432, matching docker-compose, so a Postgres already running on the
#: default port is not quietly the one the tests write to.
DEFAULT_URL = "postgresql+psycopg://discern:discern@localhost:5434/discern"


def url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


_engine = None
_factory = None


def session_factory() -> sessionmaker[Session]:
    global _engine, _factory
    if _factory is None:
        _engine = create_engine(url(), future=True)
        _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _factory


def get_db() -> Iterator[Session]:
    with session_factory()() as session:
        yield session
