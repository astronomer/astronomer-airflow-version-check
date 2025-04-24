import functools
import logging

from airflow.configuration import conf
from airflow.plugins_manager import AirflowPlugin
from airflow.utils.session import create_session
from sqlalchemy import inspect, Column, Boolean
from sqlalchemy.exc import SQLAlchemyError
from airflow.utils.sqlalchemy import UtcDateTime
from alembic.migration import MigrationContext
from alembic.operations import Operations

__version__ = "3.0.0"

log = logging.getLogger(__name__)

update_check_interval = conf.getint("astronomer", "update_check_interval", fallback=24 * 60 * 60)
eol_warning_opt_out = conf.getboolean("astronomer", "eol_warning_opt_out", fallback=False)
dismissal_period_days = conf.getint("astronomer", "eol_dismissal_period_days", fallback=7)
eol_warning_threshold_days = conf.getint("astronomer", "eol_warning_threshold_days", fallback=30)


class AstronomerVersionCheckPlugin(AirflowPlugin):
    name = "astronomer_version_check"

    @staticmethod
    def add_before_call(mod_or_cls, target, pre_fn) -> None:
        """Add a function to be called before another function in a module or class."""
        fn = getattr(mod_or_cls, target)

        @functools.wraps(fn)
        def run_before(*args, **kwargs):
            pre_fn()
            fn(*args, **kwargs)

        setattr(mod_or_cls, target, run_before)

    @classmethod
    def on_load(cls, *args, **kwargs) -> None:
        """
        Hook in to various places in Airflow in a slightly horrible
        way -- by using functools.wraps and replacing the function.
        """

        if update_check_interval == 0:
            log.debug("Skipping running update_check_plugin as [astronomer] update_check_interval = 0")
            return

        if not cls.all_table_created():
            cls.create_db_tables()
        cls.migrate_db_tables_and_reset_version_check()

        try:
            import airflow.jobs.scheduler_job

            try:
                cls.add_before_call(
                    airflow.jobs.scheduler_job.SchedulerJob, '_execute_helper', cls.start_update_thread
                )
            except AttributeError:
                cls.add_before_call(
                    airflow.jobs.scheduler_job.SchedulerJob, '_execute', cls.start_update_thread
                )
        except ImportError:
            import airflow.jobs.scheduler_job_runner

            cls.add_before_call(
                airflow.jobs.scheduler_job_runner.SchedulerJobRunner,
                '_execute',
                cls.start_update_thread,
            )

    @classmethod
    def start_update_thread(cls) -> None:
        """Start the update check thread."""
        from .models import AstronomerVersionCheck
        from .update_checks import CheckThread

        if not cls.all_table_created():
            log.warning(
                "AstronomerVersionCheck tables are missing (plugin not installed at upgradedb "
                "time?). No update checks will be performed"
            )
            return

        AstronomerVersionCheck.ensure_singleton()
        CheckThread().start()

    @classmethod
    def get_migration_columns(cls):
        """Return the columns to be added during migration."""
        from .models import AstronomerAvailableVersion

        return {
            AstronomerAvailableVersion.__tablename__: [
                Column('end_of_support', UtcDateTime(timezone=True), nullable=True),
                Column('eos_dismissed_until', UtcDateTime(timezone=True), nullable=True),
                Column('yanked', Boolean, nullable=True, default=False),
            ],
        }

    @classmethod
    def migrate_db_tables_and_reset_version_check(cls):
        """Apply migrations to the DB tables and reset the last_checked field."""
        with create_session() as session:
            columns_added = cls.create_columns_for_migration(session)
            if columns_added:
                cls.reset_last_checked(session)

    @classmethod
    def create_columns_for_migration(cls, session):
        """Create columns for the migration using Alembic."""

        engine = session.get_bind(mapper=None, clause=None)
        inspector = inspect(engine)
        if not getattr(inspector, 'has_table', None):
            inspector = engine

        migrations = cls.get_migration_columns()
        columns_added = False
        for table_name, columns in migrations.items():
            existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
            columns_to_add = [col for col in columns if col.name not in existing_columns]
            if columns_to_add:
                cls.add_columns(engine, table_name, columns_to_add)
                columns_added = True
        return columns_added

    @classmethod
    def add_columns(cls, engine, table_name, columns) -> None:
        """Add a column to a table."""
        try:
            connection = engine.connect()
            transaction = connection.begin()
            context = MigrationContext.configure(connection)
            op = Operations(context)

            for column in columns:
                op.add_column(table_name, column)
                log.info("Column %s added to %s table", column.name, table_name)

            transaction.commit()
            connection.close()
        except SQLAlchemyError as e:
            log.error("Failed to add columns to %s: %s", table_name, str(e))

    @classmethod
    def reset_last_checked(cls, session):
        """Reset the last_checked field to None in AstronomerVersionCheck."""
        from .models import AstronomerVersionCheck

        AstronomerVersionCheck.reset_last_checked()

    @classmethod
    def create_db_tables(cls):
        from .models import AstronomerAvailableVersion, AstronomerVersionCheck

        with create_session() as session:
            try:
                engine = session.get_bind(mapper=None, clause=None)
                log.info("Creating DB tables for %s", __name__)
                metadata = AstronomerVersionCheck.metadata
                metadata.create_all(
                    bind=engine,
                    tables=[
                        metadata.tables[c.__tablename__]
                        for c in [AstronomerVersionCheck, AstronomerAvailableVersion]
                    ],
                )
                log.info("Created")
            except Exception:
                log.exception("Error creating tables")
                exit(1)

    @classmethod
    def all_table_created(cls):
        """Check if there are missing tables"""
        from .models import AstronomerAvailableVersion, AstronomerVersionCheck

        tables = [AstronomerAvailableVersion, AstronomerVersionCheck]
        with create_session() as session:
            engine = session.get_bind(mapper=None, clause=None)
            inspector = inspect(engine)
            if not getattr(inspector, 'has_table', None):
                inspector = engine
            for table in tables:
                if not inspector.has_table(table.__tablename__):
                    # return early
                    return False
        return True
