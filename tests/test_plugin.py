import os
import tomllib
from pathlib import Path

import pytest
from airflow import plugins_manager


@pytest.mark.skipif(os.getenv("CIRCLE_TAG") is None, reason="CIRCLE_TAG is not set")
def test_version_matches_tag():
    tag = os.getenv("CIRCLE_TAG")

    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    version = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]["version"]

    expected = f"v{version}"
    assert tag == expected, f"Git tag {tag} does not match version {expected}"


def test_plugin_registered():
    """Verify that the plugin is registered"""
    plugins_manager.ensure_plugins_loaded()
    plugins = plugins_manager.plugins
    assert len(plugins) > 0
    assert "astronomer_version_check" in [plugin.name for plugin in plugins]


def test_logged_in(test_client):
    response = test_client.get("api/v2/dags")
    assert response.status_code == 200


def test_anon(unauthorized_test_client):
    response = unauthorized_test_client.get("api/v2/dags")
    assert response.status_code == 403


def test_table_created(caplog, monkeypatch):
    """
    Verify that the tables are created only when EXTERNAL_DB_MANAGERS is set.
    """
    from airflow.utils.db import resetdb

    # Test 1: Without EXTERNAL_DB_MANAGERS - tables should NOT be created
    monkeypatch.delenv("AIRFLOW__DATABASE__EXTERNAL_DB_MANAGERS", raising=False)
    caplog.clear()
    resetdb()
    assert "Creating VersionCheckDBManager tables from the ORM" not in caplog.text

    # Test 2: With EXTERNAL_DB_MANAGERS - tables SHOULD be created
    monkeypatch.setenv(
        "AIRFLOW__DATABASE__EXTERNAL_DB_MANAGERS",
        "astronomer.airflow.version_check.models.manager.VersionCheckDBManager",
    )
    caplog.clear()
    resetdb()
    assert "Creating VersionCheckDBManager tables from the ORM" in caplog.text
