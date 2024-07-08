import pytest
from airflow import plugins_manager
from flask import url_for
from sqlalchemy import inspect, text
from unittest.mock import patch


def drop_column_if_exists(engine, table_name, column_name):
    """Helper function to drop a column if it exists"""
    inspector = inspect(engine)
    if column_name in [col['name'] for col in inspector.get_columns(table_name)]:
        ddl = text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}")
        with engine.connect() as conn:
            conn.execute(ddl)
            conn.commit()


@patch('astronomer.airflow.version_check.plugin.AstronomerVersionCheckPlugin.insert_initial_data')
def test_plugin_registered(mock_insert_initial_data):
    """Verify that the plugin is registered"""
    mock_insert_initial_data.return_value = None
    plugins_manager.ensure_plugins_loaded()
    assert len(plugins_manager.plugins) == 1
    assert plugins_manager.plugins[0].name == 'astronomer_version_check'
    assert plugins_manager.plugins[0].flask_blueprints != []


@pytest.mark.login_as('Admin')
@patch('astronomer.airflow.version_check.plugin.AstronomerVersionCheckPlugin.insert_initial_data')
def test_logged_in(mock_insert_initial_data, client):
    mock_insert_initial_data.return_value = None
    response = client.get(url_for('Airflow.index'), follow_redirects=True)
    assert response.status_code == 200
    assert b"update-notice.css" in response.data, "Ensure our template customizations are shown"


def test_anon(client):
    response = client.get(url_for('Airflow.index'))
    assert response.status_code == 302
    assert b"update-notice.css" not in response.data, "Don't show notice when logged out"


@patch('astronomer.airflow.version_check.plugin.AstronomerVersionCheckPlugin.insert_initial_data')
def test_migrations_applied(mock_insert_initial_data, session):
    from astronomer.airflow.version_check.plugin import AstronomerVersionCheckPlugin
    from astronomer.airflow.version_check.models import AstronomerAvailableVersion

    plugins_manager.ensure_plugins_loaded()

    engine = session.get_bind()
    table_name = AstronomerAvailableVersion.__tablename__

    migration_columns = AstronomerVersionCheckPlugin.get_migration_columns()
    columns = [col.name for col in migration_columns[table_name]]

    for column in columns:
        drop_column_if_exists(engine, table_name, column)

    inspector = inspect(engine)
    existing_columns = {col['name'] for col in inspector.get_columns(table_name)}
    for column in columns:
        assert column not in existing_columns

    AstronomerVersionCheckPlugin.migrate_db_tables_and_upsert()

    inspector = inspect(engine)
    existing_columns = {col['name'] for col in inspector.get_columns(table_name)}
    for column in columns:
        assert column in existing_columns

    mock_insert_initial_data.assert_called_once()
