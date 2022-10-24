import functools
import logging

from airflow.configuration import conf
from airflow.plugins_manager import AirflowPlugin
from airflow.utils.db import create_session
from sqlalchemy import inspect

from .update_checks import UpdateAvailableBlueprint

__version__ = "1.0.13"

log = logging.getLogger(__name__)

update_check_interval = conf.getint("astronomer", "update_check_interval", fallback=24 * 60 * 60)


class AstronomerVersionCheckPlugin(AirflowPlugin):
    name = "astronomer_version_check"

    flask_blueprints = [UpdateAvailableBlueprint()] if update_check_interval != 0 else []

    @staticmethod
    def add_before_call(mod_or_cls, target, pre_fn):
        fn = getattr(mod_or_cls, target)

        @functools.wraps(fn)
        def run_before(*args, **kwargs):
            pre_fn()
            fn(*args, **kwargs)

        setattr(mod_or_cls, target, run_before)

    @classmethod
    def on_load(cls, *args, **kwargs):
        # Hook in to various places in Airflow in a slightly horrible way -- by
        # using functools.wraps and replacing the function.

        if update_check_interval == 0:
            log.debug("Skipping running update_check_plugin as [astronomer] update_check_interval = 0")
            return

        if not cls.all_table_created():
            cls.create_db_tables()

        import airflow.jobs.scheduler_job

        try:
            cls.add_before_call(
                airflow.jobs.scheduler_job.SchedulerJob, '_execute_helper', cls.start_update_thread
            )
        except AttributeError:
            cls.add_before_call(
                airflow.jobs.scheduler_job.SchedulerJob, '_run_scheduler_loop', cls.start_update_thread
            )

    @classmethod
    def start_update_thread(cls):
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
