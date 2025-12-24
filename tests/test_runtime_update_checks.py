from datetime import timedelta
from unittest import mock

import pytest
from airflow.utils.timezone import utcnow

from astronomer.airflow.version_check.models.db import AstronomerAvailableVersion, AstronomerVersionCheck
from astronomer.airflow.version_check.update_checks import (
    CheckThread,
    UpdateAvailableHelper,
    parse_new_version,
)


@pytest.mark.parametrize("image_version, new_patch_version", [("3.0-1", "3.0-2")])
@mock.patch.object(CheckThread, "_convert_runtime_versions")
def test_update_check_for_image_with_newer_patch(
    mock_convert_runtime_versions, image_version, new_patch_version, session
):
    from airflow.utils.db import resetdb

    mock_convert_runtime_versions.return_value = [
        {
            "version": "3.0-1",
            "level": "",
            "channel": "deprecated",
            "url": "",
            "description": "",
            "release_date": "2021-07-20",
            "end_of_maintenance": "2022-02-28",
            "end_of_basic_support": "2022-08-28",
            "yanked": False,
        },
        {
            "version": "3.0-2",
            "level": "",
            "channel": "deprecated",
            "url": "",
            "description": "",
            "release_date": "2021-07-20",
            "end_of_maintenance": "2022-02-28",
            "end_of_basic_support": "2022-08-28",
            "yanked": False,
        },
    ]

    with mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()

        thread = CheckThread()
        thread.ac_version = image_version
        thread.check_for_update()
        # Here we check for the highest patch on the selected image
        # If the image is 3.0-1, then the highest patch may be 3.0-2 not 4+
        latest_patch = (
            session.query(AstronomerAvailableVersion)
            .filter(AstronomerAvailableVersion.version.like(f"{new_patch_version}%"))
            .order_by(AstronomerAvailableVersion.date_released.desc())
            .first()
        )
        helper = UpdateAvailableHelper()
        result = helper.available_update()
        # UI displays the latest patch release
        assert result["version"] == latest_patch.version


@mock.patch.object(CheckThread, "_convert_runtime_versions")
def test_update_check_for_image_already_on_the_highest_patch(mock_convert_runtime_versions, session):
    from airflow.utils.db import resetdb

    mock_convert_runtime_versions.return_value = [
        {
            "version": "3.0-1",
            "level": "",
            "channel": "deprecated",
            "url": "",
            "description": "",
            "release_date": "2021-07-20",
            "end_of_maintenance": "2022-02-28",
            "end_of_basic_support": "2022-08-28",
            "yanked": False,
        },
        {
            "version": "3.0-2",
            "level": "",
            "channel": "deprecated",
            "url": "",
            "description": "",
            "release_date": "2021-07-20",
            "end_of_maintenance": "2022-02-28",
            "end_of_basic_support": "2022-08-28",
            "yanked": False,
        },
        {
            "version": "3.1-1",
            "level": "",
            "channel": "deprecated",
            "url": "",
            "description": "",
            "release_date": "2021-07-20",
            "end_of_maintenance": "2022-02-28",
            "end_of_basic_support": "2022-08-28",
            "yanked": False,
        },
    ]

    image_version = "3.0-2"
    with mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()

        thread = CheckThread()
        # pretend we are on the image_version
        thread.ac_version = image_version
        thread.check_for_update()
        available_releases = session.query(AstronomerAvailableVersion).filter(
            AstronomerAvailableVersion.hidden_from_ui.is_(False)
        )
        # Get the latest release
        highest_version = sorted(available_releases, key=lambda v: parse_new_version(v.version), reverse=True)
        helper = UpdateAvailableHelper()
        result = helper.available_update()
        # UI displays the latest release
        assert result["version"] == highest_version[0].version


@mock.patch("astronomer.airflow.version_check.update_checks.get_runtime_version")
@mock.patch.object(CheckThread, "_convert_runtime_versions")
def test_update_check_dont_show_update_if_no_new_version_available(
    mock_convert_runtime_versions, mock_runtime_version, session
):
    from airflow.utils.db import resetdb

    mock_convert_runtime_versions.return_value = [
        {
            "version": "3.0-1",
            "level": "",
            "channel": "deprecated",
            "url": "",
            "description": "",
            "release_date": "2021-07-20",
            "end_of_maintenance": "2022-02-28",
            "end_of_basic_support": "2022-08-28",
            "yanked": False,
        }
    ]

    with mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": "3.0-1"}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()
        thread = CheckThread()
        thread.runtime_version = "3.0-1"
        available_releases = thread._get_update_json().get(
            "runtimeVersionsV3",
            {
                "3.0-1": {
                    "metadata": {
                        "airflowVersion": "3.0.0",
                        "channel": "deprecated",
                        "releaseDate": "2021-07-20",
                        "endOfMaintenance": "2022-02-28",
                        "endOfBasicSupport": "2022-08-28",
                    },
                    "migrations": {"airflowDatabase": True},
                }
            },
        )

        latest_version = list(available_releases)[-1]
        public = str(latest_version)
        # Update the mock version to the highest available
        mock_runtime_version.return_value = public
        thread.runtime_version = public
        thread.check_for_update()
        helper = UpdateAvailableHelper()
        result = helper.available_update()
        # Nothing would be displayed if there is no new version available
        assert result is None


def test_alpha_beta_versions_are_not_recorded(session):
    from airflow.utils.db import resetdb

    with mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": "3.0-1"}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()

        thread = CheckThread()
        thread.ac_version = "4.0-1"
        available_releases = thread._get_update_json().get(
            "runtimeVersionsV3",
            {
                "3.0-1-nightly20250220": {
                    "metadata": {
                        "airflowVersion": "3.0.0",
                        "channel": "alpha",
                        "releaseDate": "2025-02-20",
                        "endOfMaintenance": "2025-02-19",
                        "endOfBasicSupport": "2025-08-19",
                    },
                    "migrations": {"airflowDatabase": True},
                }
            },
        )
        alpha_beta = [k for k, v in available_releases.items() if v["metadata"]["channel"] in ["alpha", "beta"]]
        thread.check_for_update()
        recorded = session.query(AstronomerAvailableVersion).all()
        recorded = [r.version for r in recorded]
        for item in alpha_beta:
            assert item not in recorded


def test_plugin_table_created(session):
    import threading

    from airflow.cli.commands.standalone_command import standalone
    from sqlalchemy import inspect

    from astronomer.airflow.version_check.models.db import AstronomerVersionCheck

    engine = session.get_bind(mapper=None, clause=None)
    inspector = inspect(engine)
    table_name = AstronomerVersionCheck.__tablename__
    with mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": "5.0.0"}):
        thread = threading.Thread(target=standalone, args=("webserver",))
        thread.daemon = True
        thread.start()
        while thread.is_alive():
            if inspector.has_table("task_instance"):
                break
        for _ in range(10):
            x = inspector.has_table(table_name)
        assert x
        thread.join(timeout=1)


@pytest.mark.parametrize(
    "image_version, eom_days_offset, expected_level, expected_days_remaining",
    [("3.0-1", 10, "warning", 10), ("3.0-1", -1, "critical", -1)],
)
def test_days_to_eom_warning_and_critical(
    session, image_version, eom_days_offset, expected_level, expected_days_remaining
):
    """Test End of Maintenance (EOM) warnings at different day offsets."""
    from airflow.utils.db import resetdb

    end_of_maintenance_date = utcnow() + timedelta(days=eom_days_offset)
    with mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()

        av = AstronomerAvailableVersion(
            version=image_version,
            level="",
            date_released=utcnow() - timedelta(days=100),
            description="",
            url="",
            hidden_from_ui=False,
            end_of_maintenance=end_of_maintenance_date,
        )
        session.add(av)
        session.commit()

        helper = UpdateAvailableHelper()
        result = helper.available_eom()

        assert result is not None
        assert abs(result["days_remaining"] - expected_days_remaining) <= 1
        assert result["level"] == expected_level
        assert result["type"] == "eom"


@pytest.mark.parametrize(
    "image_version, eobs_days_offset, expected_level, expected_days_remaining",
    [("3.0-1", 10, "warning", 10), ("3.0-1", -1, "critical", -1)],
)
def test_days_to_eobs_warning_and_critical(
    session, image_version, eobs_days_offset, expected_level, expected_days_remaining
):
    """Test End of Basic Support (EOBS) warnings at different day offsets."""
    from airflow.utils.db import resetdb

    end_of_basic_support_date = utcnow() + timedelta(days=eobs_days_offset)
    with mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()

        av = AstronomerAvailableVersion(
            version=image_version,
            level="",
            date_released=utcnow() - timedelta(days=100),
            description="",
            url="",
            hidden_from_ui=False,
            end_of_basic_support=end_of_basic_support_date,
        )
        session.add(av)
        session.commit()

        helper = UpdateAvailableHelper()
        result = helper.available_eobs()

        assert result is not None
        assert abs(result["days_remaining"] - expected_days_remaining) <= 1
        assert result["level"] == expected_level
        assert result["type"] == "eobs"


def test_priority_warning_yanked_takes_precedence(session):
    """Test that yanked warning takes precedence over EOM and EOBS."""
    from airflow.utils.db import resetdb

    image_version = "3.0-1"
    with mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()

        # Create a version that is yanked AND has EOM/EOBS warnings
        av = AstronomerAvailableVersion(
            version=image_version,
            level="",
            date_released=utcnow() - timedelta(days=100),
            description="",
            url="",
            hidden_from_ui=False,
            end_of_maintenance=utcnow() + timedelta(days=5),
            end_of_basic_support=utcnow() + timedelta(days=10),
            yanked=True,
        )
        session.add(av)
        session.commit()

        helper = UpdateAvailableHelper()
        result = helper.get_priority_warning()

        assert result is not None
        assert result["type"] == "yanked"
        assert result["level"] == "critical"


def test_priority_warning_eobs_over_eom(session):
    """Test that EOBS warning takes precedence over EOM warning."""
    from airflow.utils.db import resetdb

    image_version = "3.0-1"
    with mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()

        # Create a version with both EOM and EOBS warnings active
        av = AstronomerAvailableVersion(
            version=image_version,
            level="",
            date_released=utcnow() - timedelta(days=100),
            description="",
            url="",
            hidden_from_ui=False,
            end_of_maintenance=utcnow() + timedelta(days=5),
            end_of_basic_support=utcnow() + timedelta(days=10),
            yanked=False,
        )
        session.add(av)
        session.commit()

        helper = UpdateAvailableHelper()
        result = helper.get_priority_warning()

        assert result is not None
        assert result["type"] == "eobs"


@pytest.mark.parametrize(
    "image_version, yanked",
    [("3.0-1", True), ("3.0-1", False)],
)
def test_yanked_version_excluded_from_updates(session, image_version, yanked):
    from airflow.utils.db import resetdb

    with mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()

        av = AstronomerAvailableVersion(
            version=image_version,
            level="",
            date_released=utcnow() - timedelta(days=100),
            description="",
            url="",
            hidden_from_ui=False,
            yanked=yanked,
        )
        session.add(av)
        session.commit()

        helper = UpdateAvailableHelper()
        result = helper.available_update()

        if yanked:
            assert result is None
        else:
            assert result["version"] == image_version
            assert "yanked" not in result


@pytest.mark.parametrize(
    "image_version, yanked",
    [("3.0-1", True), ("3.0-1", False)],
)
def test_available_yanked(session, image_version, yanked):
    from airflow.utils.db import resetdb

    with mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()

        av = AstronomerAvailableVersion(
            version=image_version,
            level="",
            date_released=utcnow() - timedelta(days=100),
            description="",
            url="",
            hidden_from_ui=False,
            yanked=yanked,
        )
        session.add(av)
        session.commit()

        helper = UpdateAvailableHelper()
        result = helper.available_yanked()

        if yanked:
            assert result is not None
            assert image_version in result
        else:
            assert result is None
