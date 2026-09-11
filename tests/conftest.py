"""Service tests run against a real Postgres, because the thing under test is a schema.

An in-memory SQLite would not exercise the unique constraint the same way, would not have
timezone-aware timestamps, and would not catch a migration that is wrong. Testing the fake
would prove nothing about the thing that ships.
"""

from __future__ import annotations

import pytest

TOKEN = "test-token-not-a-secret"


@pytest.fixture(scope="session", autouse=True)
def schema():
    from discern.service.db import session_factory
    from discern.service.models import Base

    engine = session_factory().kw["bind"]
    Base.metadata.create_all(engine)


@pytest.fixture
def db():
    from discern.service.db import session_factory

    with session_factory()() as session:
        yield session
        session.rollback()


@pytest.fixture(autouse=True)
def clean(db):
    from sqlalchemy import text

    # Every test owns the whole history, so one cannot leak into another's comparison.
    db.execute(text("TRUNCATE result, run RESTART IDENTITY CASCADE"))
    db.commit()


@pytest.fixture
def client(db, monkeypatch):
    """The real app, with the session the other fixtures use and a known token."""
    from fastapi.testclient import TestClient

    from discern.service.app import app
    from discern.service.db import get_db

    monkeypatch.setenv("DISCERN_TOKEN", TOKEN)
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def token() -> str:
    """The token the service is started with, for the tests that send it wrongly on purpose."""
    return TOKEN
