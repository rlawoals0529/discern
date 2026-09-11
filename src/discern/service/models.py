"""Stored runs, so "did this get better since last week" is answerable.

A single run is a CLI concern and needs no database. Comparing two runs a fortnight apart is
not, and it is the question people actually have.

The shape follows the one rule the rest of the package is built on: **the three outcomes are
stored, not a pass rate.** Storing a rate would make the errored and skipped items
unrecoverable, and every honest thing this tool says about a run depends on still being able
to tell those apart. A rate is derived on the way out, never on the way in.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Run(Base):
    """One evaluation of one configuration over a suite."""

    __tablename__ = "run"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: What was being evaluated. Free text, because it is a label a person chose.
    label: Mapped[str] = mapped_column(String(200), index=True)
    #: Which suite. Two runs of different suites are not comparable, and this is how the
    #: service can say so rather than pairing on item ids that happen to collide.
    suite: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=text("now()")
    )

    results: Mapped[list[Result]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )


class Result(Base):
    """One item, once, in one run."""

    __tablename__ = "result"
    __table_args__ = (
        # The same item cannot appear twice in one run. A duplicate would make one of the two
        # invisible to the paired comparison, which is the failure the suite loader also
        # refuses at the other end.
        UniqueConstraint("run_id", "item_id", name="uq_result_run_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(String(200), index=True)
    #: passed, failed, errored or skipped. Stored as written so a fifth is a migration and
    #: not a silent coercion into one of the four.
    outcome: Mapped[str] = mapped_column(String(16))
    #: Present only for errored. A rate limit and a grader crash are different problems.
    error: Mapped[str | None] = mapped_column(Text, default=None)
    duration_ms: Mapped[int | None] = mapped_column(default=None)

    run: Mapped[Run] = relationship(back_populates="results")
