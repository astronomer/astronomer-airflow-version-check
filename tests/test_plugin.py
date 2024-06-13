import pytest
from airflow import plugins_manager
from flask import url_for
from sqlalchemy import inspect


def test_plugin_registered():
    """Verify that the plugin is registered"""
    plugins_manager.ensure_plugins_loaded()
    assert len(plugins_manager.plugins) == 1
    assert plugins_manager.plugins[0].name == 'astronomer_version_check'
    assert plugins_manager.plugins[0].flask_blueprints != []


@pytest.mark.login_as('Admin')
def test_logged_in(client):
    response = client.get(url_for('Airflow.index'), follow_redirects=True)
    assert response.status_code == 200
    assert b"update-notice.css" in response.data, "Ensure our template customizations are shown"


def test_anon(client):
    response = client.get(url_for('Airflow.index'))
    assert response.status_code == 302
    assert b"update-notice.css" not in response.data, "Don't show notice when logged out"


def test_migrations_applied(session):
    """Verify that the migrations are applied correctly"""
    from astronomer.airflow.version_check.plugin import AstronomerVersionCheckPlugin
    from astronomer.airflow.version_check.models import AstronomerAvailableVersion

    plugins_manager.ensure_plugins_loaded()
    AstronomerVersionCheckPlugin.migrate_db_tables()
    inspector = inspect(session.get_bind())
    columns = {col['name'] for col in inspector.get_columns(AstronomerAvailableVersion.__tablename__)}
    assert 'end_of_support' in columns, "Ensure the 'end_of_support' column is added"
