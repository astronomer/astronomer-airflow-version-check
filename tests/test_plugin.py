import os

from airflow import plugins_manager


def test_plugin_registered():
    """Verify that the plugin is registered"""
    plugins_manager.ensure_plugins_loaded()
    plugins = plugins_manager.plugins
    assert len(plugins) > 0
    assert 'astronomer_version_check' in [plugin.name for plugin in plugins]


def test_logged_in(test_client):
    response = test_client.get('api/v2/dags')
    assert response.status_code == 200


def test_anon(unauthorized_test_client):
    response = unauthorized_test_client.get("api/v2/dags")
    assert response.status_code == 403


def test_table_created(caplog):
    """
    Verify that the tables are created
    """
    from airflow.utils.db import resetdb

    caplog.clear()
    resetdb()
    assert 'Creating VersionCheckDBManager tables from the ORM' in caplog.text
    os.environ.pop('AIRFLOW__DATABASE__EXTERNAL_DB_MANAGERS', None)
    caplog.clear()
    resetdb()

    assert 'Creating VersionCheckDBManager tables from the ORM' not in caplog.text
