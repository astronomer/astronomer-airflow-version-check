import functools
import logging

from airflow.configuration import conf
from airflow.plugins_manager import AirflowPlugin
from airflow.utils.db import create_session
from sqlalchemy import inspect, Column, MetaData, Table
from airflow.utils.sqlalchemy import UtcDateTime

from .update_checks import UpdateAvailableBlueprint

__version__ = "2.0.3"

log = logging.getLogger(__name__)

update_check_interval = conf.getint("astronomer", "update_check_interval", fallback=24 * 60 * 60)


class AstronomerVersionCheckPlugin(AirflowPlugin):
    name = "astronomer_version_check"

    flask_blueprints = [UpdateAvailableBlueprint()] if update_check_interval != 0 else []

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
        cls.migrate_db_tables()

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
    def migrate_db_tables(cls):
        """Apply migrations to the DB tables."""
        with create_session() as session:
            cls.apply_migrations(session)

    @classmethod
    def apply_migrations(cls, session):
        """Apply migrations to the DB tables."""
        from .models import AstronomerAvailableVersion

        engine = session.get_bind(mapper=None, clause=None)
        inspector = inspect(engine)
        if not getattr(inspector, 'has_table', None):
            inspector = engine

        migrations = {
            AstronomerAvailableVersion.__tablename__: {
                'end_of_support': Column('end_of_support', UtcDateTime(timezone=True), nullable=True)
            }
        }

        for table_name, columns in migrations.items():
            existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
            for column_name, column_obj in columns.items():
                if column_name not in existing_columns:
                    cls.add_column(engine, table_name, column_obj)

    @staticmethod
    def add_column(engine, table_name, column_obj) -> None:
        """Add a column to a table."""
        log.info(f"Adding column {column_obj.name} to {table_name} table")
        metadata = MetaData()
        table = Table(table_name, metadata, autoload_with=engine)
        column_obj.create(table)
        log.info(f"Added column {column_obj.name}")

    @classmethod
    def create_db_tables(cls) -> None:
        """Create the DB tables."""
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
    def all_table_created(cls) -> bool:
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
