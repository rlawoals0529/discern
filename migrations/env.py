"""Alembic, pointed at the same URL and the same metadata the service uses.

Both of those matter. A migration environment with its own connection string is how a schema
gets applied to a database nobody is reading, and its own metadata is how autogenerate starts
proposing to drop tables it cannot see.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from discern.service.db import url
from discern.service.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
