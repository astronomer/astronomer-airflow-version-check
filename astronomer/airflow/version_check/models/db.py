from __future__ import annotations

import os
import logging
import threading
from typing import TYPE_CHECKING

import sqlalchemy.ext
from sqlalchemy import Boolean, Column, Index, MetaData, String, Text, or_
from sqlalchemy.orm import declarative_base
from airflow.models.base import _get_schema, naming_convention
from airflow.utils.session import create_session
from airflow.utils.net import get_hostname
from airflow.utils.timezone import utcnow
from airflow.utils.sqlalchemy import UtcDateTime

if TYPE_CHECKING:
    from datetime import timedelta
    from sqlalchemy.orm import Session


log = logging.getLogger(__name__)

metadata = MetaData(schema=_get_schema(), naming_convention=naming_convention)
Base = declarative_base(metadata=metadata)


class AstronomerVersionCheck(Base):
    __tablename__ = "astro_version_check"
    singleton = Column(Boolean, default=True, nullable=False, primary_key=True)

    # For information only
    last_checked = Column(UtcDateTime(timezone=True))
    last_checked_by = Column(Text)

    @classmethod
    def ensure_singleton(cls):
        """
        Ensure that the singleton row exists in this table
        """
        with create_session() as session:
            # To keep PG logs quieter (it shows an ERROR for the PK violation),
            # we try and select first
            if session.query(cls).get({"singleton": True}) is not None:
                return

            try:
                session.bulk_save_objects([cls(singleton=True)])
            except sqlalchemy.exc.IntegrityError:
                # Already exists, we're good
                session.rollback()

    @classmethod
    def acquire_lock(cls, check_interval: timedelta, session: Session) -> AstronomerVersionCheck | None:
        """
        Acquire an exclusive lock to perform an update check if the check is due
        and if another check is not already in progress.

        We use the database to hold the lock for as long as this transaction is open using `FOR UPDATE SKIP LOCKED`.

        This method will either return a row meaning the check is due and we
        have acquired the lock. The lock will be held for the duration of the
        database transaction -- be careful to to close this before you are
        done!

        This will throw an error if the lock is held by another transaction.
        """
        now = utcnow()

        return (
            session.query(cls)
            .filter(
                cls.singleton.is_(True),
                or_(cls.last_checked.is_(None), cls.last_checked <= now - check_interval),
            )
            .with_for_update(nowait=True)
            .one_or_none()
        )

    @classmethod
    def get(cls, session):
        """
        Return the update tracking row
        """
        return session.query(cls).filter(cls.singleton.is_(True)).one()

    @staticmethod
    def host_identifier():
        return f"{get_hostname()}-{os.getpid()}#{threading.get_ident()}"

    @classmethod
    def reset_last_checked(cls):
        """
        Reset the last_checked field to None for the singleton row
        """
        with create_session() as session:
            row = session.query(cls).filter(cls.singleton.is_(True)).one()
            row.last_checked = None


class AstronomerAvailableVersion(Base):
    __tablename__ = "astro_available_version"
    version = Column(Text().with_variant(String(255), "mysql"), nullable=False, primary_key=True)
    level = Column(Text, nullable=False)
    date_released = Column(UtcDateTime(timezone=True), nullable=False)
    description = Column(Text)
    url = Column(Text)
    hidden_from_ui = Column(Boolean, default=False, nullable=False)
    end_of_support = Column(UtcDateTime(timezone=True), nullable=True)
    eos_dismissed_until = Column(UtcDateTime(timezone=True), nullable=True)
    yanked = Column(Boolean, default=False, nullable=True)

    __table_args__ = (Index("idx_astro_available_version_hidden", hidden_from_ui),)
