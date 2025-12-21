from __future__ import annotations

import enum
import json
import os
import platform
import random
import re
import sys
import threading
import time
from datetime import timedelta
from functools import wraps
from typing import Any, Callable, Sequence, TypeVar, cast

import distro
import pendulum
import requests
import sqlalchemy.exc
from airflow.configuration import conf
from airflow.utils.log.logging_mixin import LoggingMixin
from airflow.utils.session import create_session
from airflow.utils.timezone import utcnow
from flask import flash, g, redirect, render_template, request
from requests.exceptions import HTTPError, SSLError
from semver import Version as version
from sqlalchemy import or_

T = TypeVar("T", bound=Callable)

# Code is placed in this file as the default Airflow logging config shows the
# file name (not the logger name) so this prefixes our log messages with
# "update_checks.py"


def has_access_(permissions: Sequence[tuple[str, str]]) -> Callable[[T], T]:
    method: str = permissions[0][0]
    resource_type: str = permissions[0][1]

    from airflow.api_fastapi.app import get_auth_manager
    from airflow.utils.net import get_hostname

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


def parse_new_version(version_str):
    """
    Parse versions like '3.0-1-nightly20241216'.
    """
    # Extract major, minor, patch and metadata from version
    match = re.match(r"(\d+)\.(\d+)(?:-(\d+))?", version_str)
    major, minor, patch = match.groups()
    return version.parse(f"{major}.{minor}.{patch}")


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
        self.base_url = conf.get("api", "base_url", fallback="/")
        self.runtime_version = get_runtime_version()
        self.update_url = conf.get(
            "astronomer", "update_url", fallback="https://updates.astronomer.io/astronomer-runtime"
        )

        if conf.getboolean("astronomer", "_fake_check", fallback=False):
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
        from astronomer.airflow.version_check.models.db import AstronomerAvailableVersion

        with create_session() as session:
            available_releases = session.query(AstronomerAvailableVersion).filter(
                AstronomerAvailableVersion.hidden_from_ui.is_(False)
            )

            runtime_version = parse_new_version(get_runtime_version())
            for rel in available_releases:
                if runtime_version >= parse_new_version(rel.version):
                    rel.hidden_from_ui = True

    def check_for_update(self):
        """
        :return: The time to sleep for before the next check should be performed
        :rtype: float
        """
        from astronomer.airflow.version_check.models.db import AstronomerVersionCheck

        with create_session() as session:
            try:
                lock = AstronomerVersionCheck.acquire_lock(self.check_interval, session=session)
            except sqlalchemy.exc.OperationalError as e:
                if hasattr(e.orig, "pgcode") and e.orig.pgcode == "55P03":
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
        from astronomer.airflow.version_check.models.db import AstronomerAvailableVersion

        versions = self._convert_runtime_versions(update_document.get("runtimeVersionsV3", {}))

        current_version = parse_new_version(self.runtime_version)

        self.log.debug(
            "Raw versions in update document: %r",
            list(r["version"] for r in versions),
        )

        def parse_version(rel):
            rel["parsed_version"] = parse_new_version(rel["version"])
            return rel

        releases = map(parse_version, versions)

        for release in sorted(releases, key=lambda rel: rel["parsed_version"], reverse=True):
            parsed_ver = release["parsed_version"]
            if release["channel"] in ["alpha", "beta"]:  # ignore alpha & beta releases
                continue
            if parsed_ver < current_version:
                self.log.debug(
                    "Got to a release (%s) that is older than the running version (%s) -- stopping looking for more",
                    parsed_ver,
                    self.runtime_version,
                )
                break

            release_date = (
                pendulum.parse(release["release_date"], timezone="UTC")
                if "release_date" in release
                else pendulum.now("UTC")
            )

            end_of_maintenance = (
                pendulum.parse(release.get("end_of_maintenance"), timezone="UTC")
                if release.get("end_of_maintenance")
                else None
            )

            end_of_basic_support = (
                pendulum.parse(release.get("end_of_basic_support"), timezone="UTC")
                if release.get("end_of_basic_support")
                else None
            )

            yield AstronomerAvailableVersion(
                version=release["version"],
                level=release["level"],
                date_released=release_date,
                url=release.get("url"),
                description=release.get("description"),
                end_of_maintenance=end_of_maintenance,
                end_of_basic_support=end_of_basic_support,
                hidden_from_ui=True if parsed_ver == current_version else False,
                yanked=release.get("yanked", False),
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
                        "endOfMaintenance": "2022-02-28",
                        "endOfBasicSupport": "2022-08-28"
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
                "end_of_maintenance": "2022-02-28",
                "end_of_basic_support": "2022-08-28",
                "yanked": False
            }]
        """
        versions = []
        for k, v in runtime_versions.items():
            metadata = v["metadata"]
            new_dict = {}
            new_dict["version"] = k
            new_dict["level"] = ""
            new_dict["url"] = ""
            new_dict["description"] = ""
            new_dict["release_date"] = metadata["releaseDate"]
            new_dict["channel"] = metadata["channel"]
            new_dict["end_of_maintenance"] = metadata.get("endOfMaintenance")
            new_dict["end_of_basic_support"] = metadata.get("endOfBasicSupport")
            new_dict["yanked"] = metadata.get("yanked", False)
            versions.append(new_dict)
        return versions

    def _make_fake_runtime_response(self):
        v = parse_new_version(self.runtime_version)

        new_version = f"{v.major}.{v.minor}-{v.patch}"

        return {
            "features": {},
            "runtimeVersionsV3": {
                new_version: {
                    "metadata": {
                        "airflowVersion": "3.0.0",
                        "channel": "deprecated",
                        "releaseDate": "2021-07-20",
                        "endOfMaintenance": "2022-02-28",
                        "endOfBasicSupport": "2022-08-28",
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
                    "site": self.base_url,
                },
                headers={"User-Agent": f"airflow/{self.runtime_version} {json_data}"},
            )
            r.raise_for_status()
            return r.json()
        except (SSLError, HTTPError) as e:
            self.log.warning("Error fetching update document: %s", e)
            pass


class UpdateAvailableHelper(LoggingMixin):
    def __init__(self):
        from .plugin import (
            eobs_dismissal_period_days,
            eobs_warning_threshold_days,
            eom_dismissal_period_days,
            eom_warning_threshold_days,
        )

        self.eom_warning_threshold_days = eom_warning_threshold_days
        self.eom_dismissal_period_days = eom_dismissal_period_days
        self.eobs_warning_threshold_days = eobs_warning_threshold_days
        self.eobs_dismissal_period_days = eobs_dismissal_period_days

    def get_eom_notice(self, current_version) -> dict[str, Any] | None:
        """
        Get the End of Maintenance (EOM) notice if the current version is near or past its EOM date.

        :param current_version: The current runtime version information.
        """
        if current_version and current_version.end_of_maintenance:
            now = utcnow()
            days_to_eom = (current_version.end_of_maintenance - now).days
            if days_to_eom <= self.eom_warning_threshold_days:
                if not current_version.eom_dismissed_until or now > current_version.eom_dismissed_until:
                    level = "critical" if days_to_eom <= 0 else "warning"
                    description = "{} version {} {}.".format(
                        "Astronomer Runtime",
                        current_version.version,
                        (
                            "has reached its end of maintenance"
                            if days_to_eom <= 0
                            else f"will reach its end of maintenance in {days_to_eom} days"
                        ),
                    )
                    return {
                        "type": "eom",
                        "level": level,
                        "version": current_version.version,
                        "app_name": "Astronomer Runtime",
                        "days_remaining": days_to_eom,
                        "description": description,
                        "dismissed_until": current_version.eom_dismissed_until,
                    }
        return None

    def get_eobs_notice(self, current_version) -> dict[str, Any] | None:
        """
        Get the End of Basic Support (EOBS) notice if the current version is near or past its EOBS date.

        :param current_version: The current runtime version information.
        """
        if current_version and current_version.end_of_basic_support:
            now = utcnow()
            days_to_eobs = (current_version.end_of_basic_support - now).days
            if days_to_eobs <= self.eobs_warning_threshold_days:
                if not current_version.eobs_dismissed_until or now > current_version.eobs_dismissed_until:
                    level = "critical" if days_to_eobs <= 0 else "warning"
                    description = "{} version {} {}.".format(
                        "Astronomer Runtime",
                        current_version.version,
                        (
                            "has reached its end of basic support"
                            if days_to_eobs <= 0
                            else f"will reach its end of basic support in {days_to_eobs} days"
                        ),
                    )
                    return {
                        "type": "eobs",
                        "level": level,
                        "version": current_version.version,
                        "app_name": "Astronomer Runtime",
                        "days_remaining": days_to_eobs,
                        "description": description,
                        "dismissed_until": current_version.eobs_dismissed_until,
                    }
        return None

    def available_update(self):
        """Check if there is a new version of Astronomer Runtime available."""
        from astronomer.airflow.version_check.models.db import AstronomerAvailableVersion

        with create_session() as session:
            available_releases = session.query(AstronomerAvailableVersion).filter(
                AstronomerAvailableVersion.hidden_from_ui.is_(False),
                or_(AstronomerAvailableVersion.yanked.is_(False), AstronomerAvailableVersion.yanked.is_(None)),
            )

        runtime_version = parse_new_version(get_runtime_version())
        base_version = runtime_version.major

        sorted_releases = sorted(available_releases, key=lambda v: parse_new_version(v.version), reverse=True)
        for rel in sorted_releases:
            # Only notify about the latest release if the user is in the highest patch level.
            # On runtime:
            # if the user is on version 5.0.6 and 5.0.8, 6.0.0 are available,
            # notify the user about 5.0.8 and don't notify user about 6.0.0.
            rel_parsed_version = parse_new_version(rel.version)

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
                "level": recent_release.level,
                "date_released": recent_release.date_released,
                "description": recent_release.description,
                "version": recent_release.version,
                "url": recent_release.url,
                "app_name": "Astronomer Runtime",
            }

        return None

    def available_eom(self) -> dict[str, Any] | None:
        """Check if there is an End of Maintenance (EOM) notice for the current version."""
        from astronomer.airflow.version_check.models.db import AstronomerAvailableVersion

        from .plugin import eom_warning_opt_out

        if eom_warning_opt_out:
            return None

        with create_session() as session:
            runtime_version = get_runtime_version()
            current_version = (
                session.query(AstronomerAvailableVersion)
                .filter(AstronomerAvailableVersion.version == str(runtime_version))
                .one_or_none()
            )
            return self.get_eom_notice(current_version)

    def available_eobs(self) -> dict[str, Any] | None:
        """Check if there is an End of Basic Support (EOBS) notice for the current version."""
        from astronomer.airflow.version_check.models.db import AstronomerAvailableVersion

        from .plugin import eobs_warning_opt_out

        if eobs_warning_opt_out:
            return None

        with create_session() as session:
            runtime_version = get_runtime_version()
            current_version = (
                session.query(AstronomerAvailableVersion)
                .filter(AstronomerAvailableVersion.version == str(runtime_version))
                .one_or_none()
            )
            return self.get_eobs_notice(current_version)

    def get_priority_warning(
        self,
        current_version=None,
        eom_opt_out: bool | None = None,
        eobs_opt_out: bool | None = None,
    ) -> dict[str, Any] | None:
        """
        Get the highest priority warning for the current version.

        Priority order (highest to lowest):
        1. Yanked version (critical)
        2. End of Basic Support (EOBS) warning
        3. End of Maintenance (EOM) warning

        :param current_version: Optional AstronomerAvailableVersion object. If not provided,
            it will be fetched from the database.
        :param eom_opt_out: Optional override for EOM opt-out setting. If None, uses config.
        :param eobs_opt_out: Optional override for EOBS opt-out setting. If None, uses config.
        """
        from astronomer.airflow.version_check.models.db import AstronomerAvailableVersion

        from .plugin import eobs_warning_opt_out as config_eobs_opt_out
        from .plugin import eom_warning_opt_out as config_eom_opt_out

        eom_opt_out = eom_opt_out if eom_opt_out is not None else config_eom_opt_out
        eobs_opt_out = eobs_opt_out if eobs_opt_out is not None else config_eobs_opt_out

        if current_version is None:
            with create_session() as session:
                runtime_version = get_runtime_version()
                current_version = (
                    session.query(AstronomerAvailableVersion)
                    .filter(AstronomerAvailableVersion.version == str(runtime_version))
                    .one_or_none()
                )

        if not current_version:
            return None

        if current_version.yanked:
            return {
                "type": "yanked",
                "level": "critical",
                "message": (
                    f"Warning: Astronomer Runtime version {current_version.version} has been yanked. "
                    "We strongly recommend upgrading to a more recent supported version."
                ),
                "can_dismiss": False,
            }

        if not eobs_opt_out:
            eobs = self.get_eobs_notice(current_version)
            if eobs:
                eobs["can_dismiss"] = True
                eobs["message"] = eobs["description"]
                return eobs

        if not eom_opt_out:
            eom = self.get_eom_notice(current_version)
            if eom:
                eom["can_dismiss"] = True
                eom["message"] = eom["description"]
                return eom

        return None

    def available_yanked(self) -> str | None:
        """Check if the current version of Astronomer Runtime is yanked."""
        from astronomer.airflow.version_check.models.db import AstronomerAvailableVersion

        with create_session() as session:
            runtime_version = get_runtime_version()
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
                    f"Warning: Astronomer Runtime version {runtime_version} has been yanked. "
                    "We strongly recommend upgrading to a more recent supported version."
                )

            return None


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

    data["ci"] = True if any(name in os.environ for name in ["BUILD_BUILDID", "BUILD_ID", "CI"]) else None

    return json.dumps(data, separators=(",", ":"), sort_keys=True)
