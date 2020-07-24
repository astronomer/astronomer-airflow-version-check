import datetime
import os
import logging
import threading
from typing import Optional

import sqlalchemy.ext
from airflow.models import Base
from airflow.utils.db import create_session
from airflow.utils.net import get_hostname
from airflow.utils.timezone import utcnow
from airflow.utils.sqlalchemy import UtcDateTime
from sqlalchemy import Boolean, Column, Index, String, Text, or_

log = logging.getLogger(__name__)


class AstronomerVersionCheck(Base):
    __tablename__ = "astro_version_check"
    singleton = Column(Boolean, default=True, nullable=False, primary_key=True)

    # For infomration only
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
    def acquire_lock(cls, check_interval, session):  # type: (datetime.timedelta, sqlalchemy.Session) -> Optional[AstronomerVersionCheck]
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

        return session.query(cls).filter(
            cls.singleton.is_(True),
            or_(cls.last_checked.is_(None), cls.last_checked <= now - check_interval),
        ).with_for_update(nowait=True).one_or_none()

    @classmethod
    def get(cls, session):
        """
        Return the update tracking row
        """
        return session.query(cls).filter(cls.singleton.is_(True)).one()

    @staticmethod
    def host_identifier():
        return "{hostname}-{pid}#{tid}".format(
            hostname=get_hostname(),
            pid=os.getpid(),
            tid=threading.get_ident()
        )


class AstronomerAvailableVersion(Base):
    __tablename__ = "astro_available_version"
    version = Column(String(255), nullable=False, primary_key=True)
    level = Column(Text, nullable=False)
    date_released = Column(UtcDateTime(timezone=True), nullable=False)
    description = Column(Text)
    url = Column(Text)
    hidden_from_ui = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index('idx_astro_available_version_hidden', hidden_from_ui),
    )
