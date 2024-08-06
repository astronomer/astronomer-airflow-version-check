from __future__ import annotations
from typing import Any
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
from typing import Callable, TypeVar, cast, Sequence
from requests.exceptions import SSLError, HTTPError
from sqlalchemy import inspect, or_
from flask import Blueprint, current_app, flash, redirect, render_template, request, g
from flask_appbuilder.api import BaseApi, expose
from flask_sqlalchemy import get_state
from semver import Version as version

from airflow.configuration import conf
from airflow.utils.db import create_session
from airflow.utils.log.logging_mixin import LoggingMixin
from airflow.utils.timezone import utcnow
from functools import wraps

try:
    from airflow.www_rbac.decorators import action_logging
except ImportError:
    from airflow.www.decorators import action_logging


T = TypeVar("T", bound=Callable)

# Code is placed in this file as the default Airflow logging config shows the
# file name (not the logger name) so this prefixes our log messages with
# "update_checks.py"


def has_access_(permissions: Sequence[tuple[str, str]]) -> Callable[[T], T]:
    method: str = permissions[0][0]
    resource_type: str = permissions[0][1]

    from airflow.utils.net import get_hostname
    from airflow.www.extensions.init_auth_manager import get_auth_manager

    def decorated(*, is_authorized: bool, func: Callable, args, kwargs):
        """
        Define the behavior whether the user is authorized to access the resource.
        :param is_authorized: whether the user is authorized to access the resource
        :param func: the function to call if the user is authorized
        :param args: the arguments of ``func``
        :param kwargs: the keyword arguments ``func``
        :meta private:
        """
        if is_authorized:
            return func(*args, **kwargs)
        elif get_auth_manager().is_logged_in() and not g.user.perms:
            return (
                render_template(
                    "airflow/no_roles_permissions.html",
                    hostname=get_hostname() if conf.getboolean("webserver", "EXPOSE_HOSTNAME") else "redact",
                    logout_url=get_auth_manager().get_url_logout(),
                ),
                403,
            )
        else:
            access_denied = conf.get("webserver", "access_denied_message")
            flash(access_denied, "danger")
        return redirect(get_auth_manager().get_url_login(next=request.url))

    def has_access_decorator(func: T):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return decorated(
                is_authorized=get_auth_manager().is_authorized(method=method, resource_type=resource_type),
                func=func,
                args=args,
                kwargs=kwargs,
            )

        return cast(T, wrapper)

    return has_access_decorator


# This code is introduced to maintain backward compatibility, since with airflow > 2.8
# method `has_access` will be deprecated in airflow.www.auth.
try:
    from airflow.www.auth import has_access
except ImportError:
    has_access = has_access_


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
        self.runtime_version = get_runtime_version()
        self.update_url = conf.get(
            "astronomer", "update_url", fallback="https://updates.astronomer.io/astronomer-runtime"
        )

        if conf.getboolean('astronomer', '_fake_check', fallback=False):
            self._get_update_json = self._make_fake_runtime_response

    def run(self):
        """
        Periodically check for new versions of Astronomer Certified Airflow,
        and update the AstronomerAvailableVersions table
        """
        if self.check_interval_secs == 0:
            self.log.info("Update checks disabled")
            return

        self.hide_old_versions()

        # On start up sleep for a small amount of time (to give the scheduler time to start up properly)
        rand_delay = random.uniform(5, 20)
        self.log.debug("Waiting %d seconds before doing first check", rand_delay)
        time.sleep(rand_delay)

        while True:
            try:
                update_available, wake_up_in = self.check_for_update()
                if update_available == UpdateResult.SUCCESS_UPDATE_AVAIL:
                    self.log.info("A new version of Astronomer Runtime is available")
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

            runtime_version = version.parse(get_runtime_version())
            for rel in available_releases:
                if runtime_version >= version.parse(rel.version):
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
                "Checking for new version of Astronomer Runtime, previous check was performed at %s",
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
                    self.log.debug("Updating existing update record for %s", release.version)
                    # Update the record if needed.
                    session.merge(release)

            return result, self.check_interval.total_seconds()

    def _process_update_json(self, update_document):
        from .models import AstronomerAvailableVersion

        versions = self._convert_runtime_versions(update_document.get("runtimeVersions", {}))

        current_version = version.parse(self.runtime_version)

        self.log.debug(
            "Raw versions in update document: %r",
            list(r['version'] for r in versions),
        )

        def parse_version(rel):
            rel['parsed_version'] = version.parse(rel['version'])
            return rel

        releases = map(parse_version, versions)

        for release in sorted(releases, key=lambda rel: rel['parsed_version'], reverse=True):
            ver = version.parse(release['version'])
            if release['channel'] in ['alpha', 'beta']:  # ignore alpha & beta releases
                continue
            if ver < current_version:
                self.log.debug(
                    "Got to a release (%s) that is older than the running version (%s) -- stopping looking for more",
                    ver,
                    self.runtime_version,
                )
                break

            if 'release_date' in release:
                release_date = pendulum.parse(release['release_date'], timezone='UTC')
            else:
                release_date = utcnow()

            end_of_support = (
                pendulum.parse(release.get('end_of_support'), timezone='UTC')
                if release.get('end_of_support') is not None
                else None
            )
            if ver == current_version:
                yield AstronomerAvailableVersion(
                    version=release['version'],
                    level=release['level'],
                    date_released=release_date,
                    url=release.get('url'),
                    description=release.get('description'),
                    end_of_support=end_of_support,
                    hidden_from_ui=True,
                    yanked=release.get('yanked', False),
                )
            else:
                yield AstronomerAvailableVersion(
                    version=release['version'],
                    level=release['level'],
                    date_released=release_date,
                    url=release.get('url'),
                    description=release.get('description'),
                    end_of_support=end_of_support,
                    yanked=release.get('yanked', False),
                )

    def _convert_runtime_versions(self, runtime_versions):
        """
        Convert the runtime update document values into the format we can
        store in the database.
        runtime_versions is a dict of dicts, with the keys being the version:
             {
                "2.1.1": {
                    "metadata": {
                        "airflowVersion": "2.1.1",
                        "channel": "deprecated",
                        "releaseDate": "2021-07-20",
                        "endOfSupport": "2022-02-28"
                    },
                    "migrations": {"airflowDatabase": "true"},
                },
            }
        output:
            [{
                "version": "2.1.1",
                "level": "",
                "channel": "deprecated",
                "url": "",
                "description": "",
                "release_date": "2021-07-20",
                "end_of_support": "2022-02-28",
                "yanked": False
            }]
        """
        versions = []
        for k, v in runtime_versions.items():
            metadata = v['metadata']
            new_dict = {}
            new_dict['version'] = k
            new_dict["level"] = ""
            new_dict["url"] = ""
            new_dict["description"] = ""
            new_dict['release_date'] = metadata['releaseDate']
            new_dict['channel'] = metadata['channel']
            new_dict['end_of_support'] = metadata.get('endOfSupport')
            new_dict['yanked'] = metadata.get('yanked', False)
            versions.append(new_dict)
        return versions

    def _make_fake_runtime_response(self):
        v = version.parse(self.runtime_version)

        new_version = f'{v.major}.{v.minor}.{v.patch}'

        return {
            'features': {},
            'runtimeVersions': {
                new_version: {
                    "metadata": {
                        "airflowVersion": "2.1.1",
                        "channel": "deprecated",
                        "releaseDate": "2021-07-20",
                        "endOfSupport": "2022-02-28",
                        "yanked": False,
                    },
                    "migrations": {"airflowDatabase": "true"},
                },
            },
        }

    def _get_update_json(self):  # pylint: disable=E0202
        json_data = get_user_string_data()
        try:
            r = requests.get(
                self.update_url,
                timeout=self.request_timeout,
                params={
                    'site': self.base_url,
                },
                headers={'User-Agent': f'airflow/{self.runtime_version} {json_data}'},
            )
            r.raise_for_status()
            return r.json()
        except (SSLError, HTTPError) as e:
            self.log.warning("Error fetching update document: %s", e)
            pass


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
        from .plugin import dismissal_period_days, eol_warning_threshold_days

        self.eol_warning_threshold_days = eol_warning_threshold_days
        self.dismissal_period_days = dismissal_period_days

    def get_eol_notice(self, current_version) -> dict[str, Any] | None:
        """
        Get the EOL notice information if the current version is near or past its EOL.

        :param current_version: The current runtime version information.
        """
        if current_version and current_version.end_of_support:
            now = utcnow()
            days_to_eol = (current_version.end_of_support - now).days
            if days_to_eol <= self.eol_warning_threshold_days:
                if not current_version.eos_dismissed_until or now > current_version.eos_dismissed_until:
                    eol_level = 'critical' if days_to_eol <= 0 else 'warning'
                    description = "{} version {} {}.".format(
                        "Astronomer Runtime",
                        current_version.version,
                        "has reached its end of life"
                        if days_to_eol <= 0
                        else "will reach its end of life in %d days" % days_to_eol,
                    )
                    return {
                        "level": eol_level,
                        "version": current_version.version,
                        "app_name": "Astronomer Runtime",
                        "days_to_eol": days_to_eol,
                        "description": description,
                        "dismissed_until": current_version.eos_dismissed_until,
                    }
        return None

    def available_update(self):
        """Check if there is a new version of Astronomer Runtime available."""
        from .models import AstronomerAvailableVersion

        session = get_state(app=current_app).db.session
        available_releases = session.query(AstronomerAvailableVersion).filter(
            AstronomerAvailableVersion.hidden_from_ui.is_(False),
            or_(AstronomerAvailableVersion.yanked.is_(False), AstronomerAvailableVersion.yanked.is_(None)),
        )

        runtime_version = version.parse(get_runtime_version())
        base_version = runtime_version.major

        sorted_releases = sorted(available_releases, key=lambda v: version.parse(v.version), reverse=True)
        for rel in sorted_releases:
            # Only notify about the latest release if the user is in the highest patch level.
            # On runtime:
            # if the user is on version 5.0.6 and 5.0.8, 6.0.0 are available,
            # notify the user about 5.0.8 and don't notify user about 6.0.0.
            rel_parsed_version = version.parse(rel.version)

            rel_parsed_base_version = rel_parsed_version.major
            if rel_parsed_version > runtime_version and rel_parsed_base_version == base_version:
                return {
                    "level": rel.level,
                    "date_released": rel.date_released,
                    "description": rel.description,
                    "version": rel.version,
                    "url": rel.url,
                    "app_name": "Astronomer Runtime",
                }

        if sorted_releases:
            recent_release = sorted_releases[0]
            return {
                'level': recent_release.level,
                'date_released': recent_release.date_released,
                'description': recent_release.description,
                'version': recent_release.version,
                'url': recent_release.url,
                "app_name": "Astronomer Runtime",
            }

        return None

    def available_eol(self) -> dict[str, Any] | None:
        """Check if there is an EOL notice for the current version of Astronomer Runtime."""
        from .plugin import eol_warning_opt_out
        from .models import AstronomerAvailableVersion

        if eol_warning_opt_out:
            return None

        session = get_state(app=current_app).db.session
        runtime_version = version.parse(get_runtime_version())
        current_version = (
            session.query(AstronomerAvailableVersion)
            .filter(AstronomerAvailableVersion.version == str(runtime_version))
            .one_or_none()
        )
        return self.get_eol_notice(current_version)

    def available_yanked(self) -> dict[str, Any] | None:
        """Check if the current version of Astronomer Runtime is yanked."""
        from .models import AstronomerAvailableVersion

        session = get_state(app=current_app).db.session
        runtime_version = version.parse(get_runtime_version())
        current_version = (
            session.query(AstronomerAvailableVersion)
            .filter(
                AstronomerAvailableVersion.version == str(runtime_version),
                AstronomerAvailableVersion.yanked.is_(True),
            )
            .one_or_none()
        )

        if current_version and current_version.yanked:
            return (
                f"Warning: This version of Astronomer Runtime, {runtime_version}, has been yanked. "
                "Please refer to the "
                "<a href='https://www.astronomer.io/docs/astro/runtime-version-lifecycle-policy#restricted-runtime-versions' "
                "target='_blank'>documentation</a> for more details."
            )

        return None

    def new_template_vars(self):
        return {
            # Fetch it once per template render, not each time it's accessed
            'cea_update_available': lazy_object_proxy.Proxy(self.available_update),
            'cea_eol_notice': lazy_object_proxy.Proxy(self.available_eol),
            'cea_yanked_warning': lazy_object_proxy.Proxy(self.available_yanked),
            'airflow_base_template': self.airflow_base_template,
        }

    class UpdateAvailable(BaseApi):
        resource_name = "update_available"
        csrf_exempt = False
        base_permissions = ['can_dismiss']
        # A bug in Flask-AppBuilder mandates us to have a value for method_permission_name
        # before is_item_public filter can be used.
        method_permission_name = {
            "dismiss": "dismiss",
            "dismiss_eol": "dismiss_eol",
        }
        allow_browser_login = True

        @expose("<path:version>/dismiss_eol", methods=["POST"])
        @has_access([("can_dismiss", 'UpdateAvailable')])
        @action_logging
        def dismiss_eol(self, version):
            from .plugin import dismissal_period_days
            from .models import AstronomerAvailableVersion

            dismiss_until = utcnow() + timedelta(days=dismissal_period_days)

            with create_session() as session:
                session.query(AstronomerAvailableVersion).filter(
                    AstronomerAvailableVersion.version == version,
                ).update(
                    {AstronomerAvailableVersion.eos_dismissed_until: dismiss_until}, synchronize_session=False
                )

            return self.response(200)

        @expose("<path:version>/dismiss", methods=["POST"])
        @has_access(
            [
                ("can_dismiss", 'UpdateAvailable'),
            ]
        )
        @action_logging
        def dismiss(self, version):
            from .models import AstronomerAvailableVersion

            with create_session() as session:
                session.query(AstronomerAvailableVersion).filter(
                    AstronomerAvailableVersion.version == version,
                ).update({AstronomerAvailableVersion.hidden_from_ui: True}, synchronize_session=False)

            return self.response(200)

    def register(self, app, *args, **kwargs):
        """
        Re-configure Flask to use our customized layout (that includes the call-home JS)
        Called by Flask when registering the blueprint to the app
        """
        from .models import AstronomerVersionCheck

        if not hasattr(app, 'appbuilder'):
            return

        with create_session() as session:
            engine = session.get_bind(mapper=None, clause=None)
            inspector = inspect(engine)
            if not getattr(inspector, 'has_table', None):
                inspector = engine
            if not inspector.has_table(AstronomerVersionCheck.__tablename__):
                self.log.warning(
                    "AstronomerVersionCheck tables are missing (plugin not installed at upgradedb "
                    "time?). No update checks will be performed"
                )
                return

        self.airflow_base_template = app.appbuilder.base_template

        if app.appbuilder.base_template in ["airflow/master.html", "airflow/main.html", "runtime_base.html"]:
            app.appbuilder.base_template = "astro-baselayout.html"
        else:
            self.log.warning(
                "Not replacing appbuilder.base_template, it didn't have the expected value. Update"
                " available messages will not be visible in UI"
            )
        app.appbuilder.add_view_no_menu(self.UpdateAvailable)
        self.app_context_processor(self.new_template_vars)

        super().register(app, *args, **kwargs)


def get_runtime_version():
    return os.environ.get("ASTRONOMER_RUNTIME_VERSION", None)


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
