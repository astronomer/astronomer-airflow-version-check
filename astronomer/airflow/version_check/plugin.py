import functools
import logging

from airflow.configuration import conf
from airflow.plugins_manager import AirflowPlugin
from airflow.utils.session import create_session
from sqlalchemy import inspect

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
            log.warning(
                "AstronomerVersionCheck tables are missing please ensure to add VersionCheckDBManager "
                "to AIRFLOW__DATABASE__EXTERNAL_DB_MANAGERS configuration. No update checks will be performed"
            )
            return

        from airflow.jobs.scheduler_job_runner import SchedulerJobRunner

        cls.add_before_call(
            SchedulerJobRunner,
            "_execute",
            cls.start_update_thread,
        )

    @classmethod
    def start_update_thread(cls) -> None:
        """Start the update check thread."""
        from astronomer.airflow.version_check.models.db import AstronomerVersionCheck

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
    def all_table_created(cls):
        """Check if there are missing tables"""
        from astronomer.airflow.version_check.models.db import (
            AstronomerAvailableVersion,
            AstronomerVersionCheck,
        )

        tables = [AstronomerAvailableVersion, AstronomerVersionCheck]
        with create_session() as session:
            engine = session.get_bind(mapper=None, clause=None)
            inspector = inspect(engine)
            if not getattr(inspector, "has_table", None):
                inspector = engine
            for table in tables:
                if not inspector.has_table(table.__tablename__):
                    # return early
                    return False
        return True
