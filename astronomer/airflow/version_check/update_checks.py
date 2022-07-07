import enum
import json
import os
import platform
import random
import sys
import threading
import time
from datetime import timedelta

import distro
import lazy_object_proxy
import pendulum
import requests
import sqlalchemy.exc
from flask import Blueprint, current_app
from flask_appbuilder.api import BaseApi, expose
from flask_appbuilder.security.decorators import protect
from flask_sqlalchemy import get_state
from packaging import version

from airflow.configuration import conf
from airflow.utils.db import create_session
from airflow.utils.log.logging_mixin import LoggingMixin
from airflow.utils.timezone import utcnow
from airflow import __version__ as AIRFLOW_VERSION

try:
    from airflow.www_rbac.decorators import action_logging
except ImportError:
    from airflow.www.decorators import action_logging


# Code is placed in this file as the default Airflow logging config shows the
# file name (not the logger name) so this prefixes our log messages with
# "update_checks.py"


class UpdateResult(enum.Enum):
    FAILURE = enum.auto()
    NOT_DUE = enum.auto()
    SUCCESS_NO_UPDATE = enum.auto()
    SUCCESS_UPDATE_AVAIL = enum.auto()


class CheckThread(threading.Thread, LoggingMixin):
    def __init__(self):
        super().__init__(name="AstronomerCEAVersionCheckThread", daemon=True)
        # Check once a day by default
        self.check_interval_secs = conf.getint("astronomer", "update_check_interval", fallback=24 * 60 * 60)
        self.check_interval = timedelta(seconds=self.check_interval_secs)
        self.request_timeout = conf.getint("astronomer", "update_check_timeout", fallback=60)
        self.base_url = conf.get("webserver", "base_url")

        self.update_url = conf.get(
            "astronomer", "update_url", fallback="https://updates.astronomer.io/astronomer-certified"
        )

        if conf.getboolean('astronomer', '_fake_check', fallback=False):
            self._get_update_json = self._make_fake_response

    def run(self):
        """
        Periodically check for new versions of Astronomer Certified Airflow,
        and update the AstronomerAvailableVersions table
        """
        if self.check_interval_secs == 0:
            self.log.info("Update checks disabled")
            return

        self.ac_version = get_ac_version()

        self.hide_old_versions()

        # On start up sleep for a small amount of time (to give the scheduler time to start up properly)
        rand_delay = random.uniform(5, 20)
        self.log.debug("Waiting %d seconds before doing first check", rand_delay)
        time.sleep(rand_delay)
        while True:
            try:
                update_available, wake_up_in = self.check_for_update()
                if update_available == UpdateResult.SUCCESS_UPDATE_AVAIL:
                    self.log.info("A new version of Astronomer Certified Airflow is available")
                self.log.info("Check finished, next check in %s seconds", wake_up_in)
            except Exception:
                self.log.exception("Update check died with an exception, trying again in one hour")
                wake_up_in = 3600

            time.sleep(wake_up_in)

    @staticmethod
    def hide_old_versions():
        """Hide Old Versions from displaying in the UI"""
        from .models import AstronomerAvailableVersion

        with create_session() as session:
            available_releases = session.query(AstronomerAvailableVersion).filter(
                AstronomerAvailableVersion.hidden_from_ui.is_(False)
            )

            ac_version = version.parse(get_ac_version())
            for rel in available_releases:
                if ac_version >= version.parse(rel.version):
                    rel.hidden_from_ui = True

    def check_for_update(self):
        """
        :return: The time to sleep for before the next check should be performed
        :rtype: float
        """
        from .models import AstronomerVersionCheck

        with create_session() as session:
            try:
                lock = AstronomerVersionCheck.acquire_lock(self.check_interval, session=session)
            except sqlalchemy.exc.OperationalError as e:
                if hasattr(e.orig, 'pgcode') and e.orig.pgcode == '55P03':
                    self.log.debug("Could not acquire lock, or check not due, sleeping for 60s+/-10s")
                    return UpdateResult.FAILURE, random.uniform(50, 70)
                raise

            if not lock:
                next_check = AstronomerVersionCheck.get(session).last_checked + self.check_interval
                how_long = (next_check - utcnow()).total_seconds()
                self.log.debug("Next check not due until %s (%s seconds away)", next_check, how_long)
                return UpdateResult.NOT_DUE, how_long

            self.log.info(
                "Checking for new version of Astronomer Certified Airflow, previous check was performed at %s",
                lock.last_checked,
            )

            lock.last_checked = utcnow()
            lock.last_checked_by = lock.host_identifier()

            # Issue the SQL for the above update, but don't commit the transaction
            session.flush()

            result = UpdateResult.SUCCESS_NO_UPDATE

            for release in self._process_update_json(self._get_update_json()):
                if not session.query(type(release)).get(release.version):
                    self.log.info("Found %s in update document", release.version)
                    session.add(release)
                    result = UpdateResult.SUCCESS_UPDATE_AVAIL
                else:
                    self.log.debug("Updating existing update record", release.version)
                    # Update the record if needed.
                    session.merge(release)

            return result, self.check_interval.total_seconds()

    def _process_update_json(self, update_document):
        version = update_document.get('version', None)
        if version != '1.0':
            r = repr(version) if version else '<MISSING>'
            raise RuntimeError("Un-parsable format_version " + r)

        return self._process_update_json_v1_0(update_document)

    def _process_update_json_v1_0(self, update_document):
        from .models import AstronomerAvailableVersion

        current_version = version.parse(self.ac_version)

        self.log.debug(
            "Raw versions in update document: %r",
            list(r['version'] for r in update_document.get('available_releases', [])),
        )

        def parse_version(rel):
            rel['parsed_version'] = version.parse(rel['version'])
            return rel

        releases = map(parse_version, update_document.get('available_releases', []))

        for release in sorted(releases, key=lambda rel: rel['parsed_version'], reverse=True):
            ver = version.parse(release['version'])

            if ver <= current_version:
                self.log.debug(
                    "Got to a release (%s) that is older than the running version (%s) -- stopping looking for more",
                    ver,
                    self.ac_version,
                )
                break

            if 'release_date' in release:
                release_date = pendulum.parse(release['release_date'], timezone='UTC')
            else:
                release_date = utcnow()

            yield AstronomerAvailableVersion(
                version=release['version'],
                level=release['level'],
                date_released=release_date,
                url=release.get('url'),
                description=release.get('description'),
            )

    def _make_fake_response(self):
        v = version.parse(self.ac_version)

        new_version = f'{v.major}.{v.minor}.{v.micro+1}-1'

        return {
            'version': '1.0',
            'available_releases': [
                {
                    'version': new_version,
                    'url': f'https://astronomer.io/cea/release-notes/{new_version}.html',
                    'level': 'bug_fix',
                },
            ],
        }

    def _get_update_json(self):  # pylint: disable=E0202
        json_data = get_user_string_data()
        r = requests.get(
            self.update_url,
            timeout=self.request_timeout,
            params={
                'site': self.base_url,
            },
            headers={'User-Agent': f'airflow/{self.ac_version} {json_data}'},
        )

        r.raise_for_status()
        return r.json()


class UpdateAvailableBlueprint(Blueprint, LoggingMixin):

    airflow_base_template = None

    def __init__(self):
        super().__init__(
            "UpdateAvailableView",
            __name__,
            url_prefix='/astro',
            static_folder='static',
            template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        )

    def available_update(self):
        from .models import AstronomerAvailableVersion

        session = get_state(app=current_app).db.session
        available_releases = session.query(AstronomerAvailableVersion).filter(
            AstronomerAvailableVersion.hidden_from_ui.is_(False)
        )

        ac_version = version.parse(get_ac_version())
        base_version = ac_version.base_version

        sorted_releases = sorted(available_releases, key=lambda v: version.parse(v.version), reverse=True)
        for rel in sorted_releases:
            rel_parsed_version = version.parse(rel.version)
            if rel_parsed_version > ac_version and rel_parsed_version.base_version == base_version:
                return {
                    "level": rel.level,
                    "date_released": rel.date_released,
                    "description": rel.description,
                    "version": rel.version,
                    "url": rel.url,
                }

        if sorted_releases:
            recent_release = sorted_releases[0]
            return {
                'level': recent_release.level,
                'date_released': recent_release.date_released,
                'description': recent_release.description,
                'version': recent_release.version,
                'url': recent_release.url,
            }

        return None

    def new_template_vars(self):
        return {
            # Fetch it once per template render, not each time it's accessed
            'cea_update_available': lazy_object_proxy.Proxy(self.available_update),
            'airflow_base_template': self.airflow_base_template,
        }

    class UpdateAvailable(BaseApi):
        resource_name = "update_available"
        csrf_exempt = False
        base_permissions = ['can_dismiss']

        @expose("<path:version>/dismiss", methods=["POST"])
        @protect(allow_browser_login=True)
        @action_logging
        def dismiss(self, version):
            from .models import AstronomerAvailableVersion

            with create_session() as session:
                session.query(AstronomerAvailableVersion).filter(
                    AstronomerAvailableVersion.version == version,
                ).update({AstronomerAvailableVersion.hidden_from_ui: True}, synchronize_session=False)

            return self.response(200)

    def register(self, app, options):
        """
        Re-configure Flask to use our customized layout (that includes the call-home JS)
        Called by Flask when registering the blueprint to the app
        """
        from .models import AstronomerVersionCheck

        if not hasattr(app, 'appbuilder'):
            return

        with create_session() as session:
            engine = session.get_bind(mapper=None, clause=None)
            if not engine.has_table(AstronomerVersionCheck.__tablename__):
                self.log.warning(
                    "AstronomerVersionCheck tables are missing (plugin not installed at upgradedb "
                    "time?). No update checks will be performed"
                )
                return

        self.airflow_base_template = app.appbuilder.base_template

        if app.appbuilder.base_template in ["airflow/master.html", "airflow/main.html"]:
            app.appbuilder.base_template = "astro-baselayout.html"
        else:
            self.log.warning(
                "Not replacing appbuilder.base_template, it didn't have the expected value. Update"
                " available messages will not be visible in UI"
            )
        app.appbuilder.add_view_no_menu(self.UpdateAvailable)
        self.app_context_processor(self.new_template_vars)

        super().register(app, options)


def get_ac_version():
    try:
        import importlib_metadata
    except ImportError:
        from importlib import metadata as importlib_metadata

    try:
        ac_version = importlib_metadata.version('astronomer-certified')
    except importlib_metadata.PackageNotFoundError:
        # Try to work out ac_version from airflow version
        ac_version = AIRFLOW_VERSION.replace('+astro.', '-')
    return ac_version


def get_user_string_data():

    data = {
        "python": platform.python_version(),
        "implementation": {
            "name": platform.python_implementation(),
        },
        "airflow_configs": {
            "executor": conf.get("core", "executor", fallback=None),
            "store_serialized_dags": conf.get("core", "store_serialized_dags", fallback=None),
        },
    }

    if sys.platform.startswith("linux"):
        distro_infos = dict(
            filter(
                lambda x: x[1],
                zip(["name", "version", "id"], (distro.name(), distro.version(), distro.id())),
            )
        )
        if distro_infos:
            data["distro"] = distro_infos

    if sys.platform.startswith("darwin") and platform.mac_ver()[0]:
        data["distro"] = {"name": "macOS", "version": platform.mac_ver()[0]}

    if platform.system():
        data.setdefault("system", {})["name"] = platform.system()

    if platform.release():
        data.setdefault("system", {})["release"] = platform.release()

    if platform.machine():
        data["cpu"] = platform.machine()

    data["ci"] = True if any(name in os.environ for name in ['BUILD_BUILDID', 'BUILD_ID', 'CI']) else None

    return json.dumps(data, separators=(",", ":"), sort_keys=True)
