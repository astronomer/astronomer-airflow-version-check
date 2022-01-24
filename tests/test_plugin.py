import pytest
from airflow import plugins_manager
from flask import url_for


def test_plugin_registered():
    """Verify that the plugin is registered"""
    plugins_manager.ensure_plugins_loaded()
    assert len(plugins_manager.plugins) == 1
    assert plugins_manager.plugins[0].name == 'astronomer_version_check'
    assert plugins_manager.plugins[0].flask_blueprints != []


@pytest.mark.xfail(condition=True, reason="Needs deeper investigation")
@pytest.mark.login_as('Admin')
def test_logged_in(client):
    response = client.get(url_for('Airflow.index'))
    assert response.status_code == 200
    assert b"update-notice.css" in response.data, "Ensure our template customizations are shown"


def test_anon(client):
    response = client.get(url_for('Airflow.index'))
    assert response.status_code == 302
    assert b"update-notice.css" not in response.data, "Don't show notice when logged out"
