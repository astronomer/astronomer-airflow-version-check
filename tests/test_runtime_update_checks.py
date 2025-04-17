from astronomer.airflow.version_check.models import AstronomerVersionCheck, AstronomerAvailableVersion
from astronomer.airflow.version_check.update_checks import (
    CheckThread,
    UpdateAvailableHelper,
    parse_new_version,
)
from unittest import mock
import pytest
from datetime import timedelta
from airflow.utils.timezone import utcnow


@pytest.fixture(autouse=True)
def mock_test_env(monkeypatch):
    monkeypatch.setenv('AIRFLOW__ASTRONOMER__UPDATE_URL', "https://updates.astronomer.io/astronomer-runtime")


@pytest.mark.parametrize("image_version, new_patch_version", [("3.0-1", "3.0-2")])
@mock.patch.object(CheckThread, '_convert_runtime_versions')
def test_update_check_for_image_with_newer_patch(
    mock_convert_runtime_versions, image_version, new_patch_version, app, session
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
            "end_of_support": "2022-02-28",
            "yanked": False,
        },
        {
            "version": "3.0-2",
            "level": "",
            "channel": "deprecated",
            "url": "",
            "description": "",
            "release_date": "2021-07-20",
            "end_of_support": "2022-02-28",
            "yanked": False,
        },
    ]

    with app.app_context(), mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
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
        assert result['version'] == latest_patch.version


@mock.patch.object(CheckThread, '_convert_runtime_versions')
def test_update_check_for_image_already_on_the_highest_patch(mock_convert_runtime_versions, app, session):
    from airflow.utils.db import resetdb

    mock_convert_runtime_versions.return_value = [
        {
            "version": "3.0-1",
            "level": "",
            "channel": "deprecated",
            "url": "",
            "description": "",
            "release_date": "2021-07-20",
            "end_of_support": "2022-02-28",
            "yanked": False,
        },
        {
            "version": "3.0-2",
            "level": "",
            "channel": "deprecated",
            "url": "",
            "description": "",
            "release_date": "2021-07-20",
            "end_of_support": "2022-02-28",
            "yanked": False,
        },
        {
            "version": "3.1-1",
            "level": "",
            "channel": "deprecated",
            "url": "",
            "description": "",
            "release_date": "2021-07-20",
            "end_of_support": "2022-02-28",
            "yanked": False,
        },
    ]

    image_version = "3.0-2"
    with app.app_context(), mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
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
        assert result['version'] == highest_version[0].version


@mock.patch('astronomer.airflow.version_check.update_checks.get_runtime_version')
@mock.patch.object(CheckThread, '_convert_runtime_versions')
def test_update_check_dont_show_update_if_no_new_version_available(
    mock_convert_runtime_versions, mock_runtime_version, app, session
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
            "end_of_support": "2022-02-28",
            "yanked": False,
        }
    ]

    with app.app_context(), mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": '3.0-1'}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()
        thread = CheckThread()
        thread.runtime_version = '3.0-1'
        available_releases = thread._get_update_json().get(
            'runtimeVersionsV3',
            {
                "3.0-1": {
                    "metadata": {
                        "airflowVersion": "3.0.0",
                        "channel": "deprecated",
                        "releaseDate": "2021-07-20",
                        "endOfSupport": "2022-02-28",
                        "LTS": False,
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


def test_alpha_beta_versions_are_not_recorded(app, session):
    from airflow.utils.db import resetdb

    with app.app_context(), mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": '3.0-1'}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()

        thread = CheckThread()
        thread.ac_version = '4.0-1'
        available_releases = thread._get_update_json().get(
            'runtimeVersionsV3',
            {
                "3.0-1-nightly20250220": {
                    "metadata": {
                        "airflowVersion": "3.0.0",
                        "channel": "alpha",
                        "releaseDate": "2025-02-20",
                        "endOfSupport": "2025-02-19",
                        "LTS": False,
                    },
                    "migrations": {"airflowDatabase": True},
                }
            },
        )
        alpha_beta = [
            k for k, v in available_releases.items() if v['metadata']['channel'] in ['alpha', 'beta']
        ]
        thread.check_for_update()
        recorded = session.query(AstronomerAvailableVersion).all()
        recorded = [r.version for r in recorded]
        for item in alpha_beta:
            assert item not in recorded


def test_plugin_table_created(app, session):
    from airflow.cli.commands.standalone_command import standalone
    from sqlalchemy import inspect
    import threading

    engine = session.get_bind(mapper=None, clause=None)
    inspector = inspect(engine)
    with app.app_context(), mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": '5.0.0'}):
        thread = threading.Thread(target=standalone, args=('webserver',))
        thread.daemon = True
        thread.start()
        while thread.is_alive():
            if inspector.has_table('task_instance'):
                break
        for _ in range(10):
            x = inspector.has_table('astro_version_check')
        assert x
        thread.join(timeout=1)


@pytest.mark.parametrize(
    "image_version, eol_days_offset, expected_level, expected_days_to_eol",
    [("3.0-1", 10, 'warning', 10), ("3.0-1", -1, 'critical', -1)],
)
def test_days_to_eol_warning_and_critical(
    app, session, image_version, eol_days_offset, expected_level, expected_days_to_eol
):
    from airflow.utils.db import resetdb

    end_of_support_date = utcnow() + timedelta(days=eol_days_offset)
    with app.app_context(), mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
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
            end_of_support=end_of_support_date,
        )
        session.add(av)
        session.commit()

        helper = UpdateAvailableHelper()
        result = helper.available_eol()

        assert abs(result['days_to_eol'] - expected_days_to_eol) <= 1
        assert result['level'] == expected_level


@pytest.mark.parametrize(
    "image_version, yanked",
    [("3.0-1", True), ("3.0-1", False)],
)
def test_yanked_version_excluded_from_updates(app, session, image_version, yanked):
    from airflow.utils.db import resetdb

    with app.app_context(), mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
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
            assert result['version'] == image_version
            assert 'yanked' not in result


@pytest.mark.parametrize(
    "image_version, yanked",
    [("3.0-1", True), ("3.0-1", False)],
)
def test_available_yanked(app, session, image_version, yanked):
    from airflow.utils.db import resetdb

    with app.app_context(), mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
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
