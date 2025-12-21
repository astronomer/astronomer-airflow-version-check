from __future__ import annotations

import functools
import logging
import sys

from airflow.configuration import conf
from airflow.plugins_manager import AirflowPlugin
from airflow.utils.session import create_session
from sqlalchemy import inspect

from astronomer.airflow.version_check.version_compat import AIRFLOW_V_3_0_PLUS

__version__ = "3.0.0"

log = logging.getLogger(__name__)

update_check_interval = conf.getint("astronomer", "update_check_interval", fallback=24 * 60 * 60)

# End of Maintenance (EOM) warning configuration
eom_warning_opt_out = conf.getboolean("astronomer", "eom_warning_opt_out", fallback=False)
eom_dismissal_period_days = conf.getint("astronomer", "eom_dismissal_period_days", fallback=7)
eom_warning_threshold_days = conf.getint("astronomer", "eom_warning_threshold_days", fallback=30)

# End of Basic Support (EOBS) warning configuration
eobs_warning_opt_out = conf.getboolean("astronomer", "eobs_warning_opt_out", fallback=False)
eobs_dismissal_period_days = conf.getint("astronomer", "eobs_dismissal_period_days", fallback=7)
eobs_warning_threshold_days = conf.getint("astronomer", "eobs_warning_threshold_days", fallback=30)

# Check if we're running on the API server
RUNNING_ON_APISERVER = (len(sys.argv) > 1 and sys.argv[1] in ["api-server"]) or (
    len(sys.argv) > 2 and "api_fastapi" in sys.argv[2]
)


def _get_base_url_path(path: str) -> str:
    """Construct URL path with webserver base_url prefix."""
    base_url = conf.get("api", "base_url", fallback="/")
    if base_url.startswith(("http://", "https://")):
        from urllib.parse import urlparse

        base_path = urlparse(base_url).path
    else:
        base_path = base_url

    base_path = base_path.rstrip("/")
    return base_path + path


def _get_api_endpoint() -> dict:
    """Get the FastAPI app configuration for the plugin."""
    from astronomer.airflow.version_check.version_api.app import create_version_check_api_app

    return {
        "app": create_version_check_api_app(),
        "url_prefix": "/version_check",
        "name": "Astronomer Version Check",
    }


class AstronomerVersionCheckPlugin(AirflowPlugin):
    name = "astronomer_version_check"

    # Register FastAPI app and React app only on API server and for Airflow 3.0+
    if RUNNING_ON_APISERVER and AIRFLOW_V_3_0_PLUS:
        fastapi_apps = [_get_api_endpoint()]

        # React apps are only supported in Airflow 3.1+
        try:
            from astronomer.airflow.version_check.version_compat import get_base_airflow_version_tuple

            if get_base_airflow_version_tuple() >= (3, 1, 0):
                react_apps = [
                    {
                        "name": "Version Check",
                        "bundle_url": _get_base_url_path("/version_check/static/main.umd.cjs"),
                        "destination": "dashboard",
                        "url_route": "version-check",
                    },
                ]
        except Exception:
            pass

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
