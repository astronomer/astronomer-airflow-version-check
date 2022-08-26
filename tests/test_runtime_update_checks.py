from astronomer.airflow.version_check.models import AstronomerVersionCheck, AstronomerAvailableVersion
from astronomer.airflow.version_check.update_checks import CheckThread, UpdateAvailableBlueprint
from unittest import mock
import pytest
from packaging import version


@pytest.fixture(autouse=True)
def mock_test_env(monkeypatch):
    monkeypatch.setenv('AIRFLOW__ASTRONOMER__UPDATE_URL', "https://updates.astronomer.io/astronomer-runtime")


@pytest.mark.parametrize("image_version, new_patch_version", [("4.0.0", "4.2.6")])
def test_update_check_for_image_with_newer_patch(image_version, new_patch_version, app, session):
    from airflow.utils.db import resetdb

    with app.app_context(), mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": image_version}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()

        thread = CheckThread()
        thread.ac_version = image_version
        thread.check_for_update()
        # Here we check for the highest patch on the selected image
        # If the image is 4.0.0, then the highest patch may be 4.2.6 not 5+
        latest_patch = (
            session.query(AstronomerAvailableVersion)
            .filter(AstronomerAvailableVersion.version.like(f"{new_patch_version}%"))
            .order_by(AstronomerAvailableVersion.date_released.desc())
            .first()
        )
        blueprint = UpdateAvailableBlueprint()
        result = blueprint.available_update()
        # UI displays the latest patch release
        assert result['version'] == latest_patch.version


def test_update_check_for_image_already_on_the_highest_patch(app, session):
    from airflow.utils.db import resetdb

    image_version = "5.0.0"
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
        highest_version = sorted(available_releases, key=lambda v: version.parse(v.version), reverse=True)
        blueprint = UpdateAvailableBlueprint()
        result = blueprint.available_update()
        # UI displays the latest release
        assert result['version'] == highest_version[0].version


@mock.patch('astronomer.airflow.version_check.update_checks.get_ac_version')
def test_update_check_dont_show_update_if_no_new_version_available(mock_ac_version, app, session):
    from airflow.utils.db import resetdb

    with app.app_context(), mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": '5.0.0'}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()
        thread = CheckThread()
        thread.ac_version = '5.0.0'
        available_releases = thread._get_update_json()['runtimeVersions']

        latest_version = list(available_releases)[-1]
        public = version.parse(latest_version).public
        # Update the mock version to the highest available
        mock_ac_version.return_value = public
        thread.ac_version = public
        thread.check_for_update()
        blueprint = UpdateAvailableBlueprint()
        result = blueprint.available_update()
        # Nothing would be displayed if there is no new version available
        assert result is None


def test_alpha_beta_versions_are_not_recorded(app, session):
    from airflow.utils.db import resetdb

    with app.app_context(), mock.patch.dict("os.environ", {"ASTRONOMER_RUNTIME_VERSION": '4.0.0'}):
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()

        thread = CheckThread()
        thread.ac_version = '4.0.0'
        available_releases = thread._get_update_json()['runtimeVersions']
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
        while thread.isAlive():
            if inspector.has_table('task_instance'):
                break
        for _ in range(10):
            x = inspector.has_table('astro_version_check')
        assert x
        thread.join(timeout=1)
