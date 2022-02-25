from astronomer.airflow.version_check.models import AstronomerVersionCheck, AstronomerAvailableVersion
from astronomer.airflow.version_check.update_checks import CheckThread, UpdateAvailableBlueprint
from unittest import mock
import pytest
from packaging import version


@pytest.mark.parametrize("image_version, lowest_tag", [("2.2.0.post2", "2.2.0"), ("2.2.3.post1", "2.2.3")])
@mock.patch('astronomer.airflow.version_check.update_checks.get_ac_version')
def test_update_check_for_image_with_newer_patch(mock_ac_version, image_version, lowest_tag, app, session):
    from airflow.utils.db import resetdb

    mock_ac_version.return_value = image_version
    with app.app_context():
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()

        thread = CheckThread()
        thread.ac_version = image_version
        thread.check_for_update()
        # Here we check for the highest patch on the selected image
        # If the image is 2.2.0.post2, then the highest patch may be 2.2.0-5
        latest_patch = (
            session.query(AstronomerAvailableVersion)
            .filter(AstronomerAvailableVersion.version.like(f"{lowest_tag}%"))
            .order_by(AstronomerAvailableVersion.date_released.desc())
            .first()
        )
        blueprint = UpdateAvailableBlueprint()
        result = blueprint.available_update()
        # UI displays the latest patch release
        assert result['version'] == latest_patch.version


@mock.patch('astronomer.airflow.version_check.update_checks.get_ac_version')
def test_update_check_for_image_already_on_the_highest_patch(mock_ac_version, app, session):
    from airflow.utils.db import resetdb

    image_version = "2.0.0.post10"
    mock_ac_version.return_value = image_version
    with app.app_context():
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

    with app.app_context():
        resetdb()
        vc = AstronomerVersionCheck(singleton=True)
        session.add(vc)
        session.commit()
        thread = CheckThread()
        thread.ac_version = "2.0.0.post10"  # just to have a value, we update it later
        # Find the highest version available
        available_releases = thread._get_update_json()['available_releases'][-1]
        public = version.parse(available_releases['version']).public
        # Update the mock version to the highest available
        mock_ac_version.return_value = public
        thread.ac_version = public
        thread.check_for_update()
        blueprint = UpdateAvailableBlueprint()
        result = blueprint.available_update()
        # Nothing would be displayed if there is no new version available
        assert result is None
