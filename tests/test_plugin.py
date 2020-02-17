from flask import url_for
import pytest


@pytest.mark.login_as('Admin')
def test_logged_in(client):
    response = client.get(url_for('Airflow.index'))
    assert response.status_code == 200
    assert b"update-notice.css" in response.data, "Ensure our template customizations are shown"


def test_anon(client):
    response = client.get(url_for('Airflow.index'))
    assert response.status_code == 302
    assert b"update-notice.css" not in response.data, "Don't show notice when logged out"
