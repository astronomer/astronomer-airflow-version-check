import datetime
import os

import pytest
import time_machine
from airflow.api_fastapi.app import create_app
from airflow.api_fastapi.auth.managers.simple.user import SimpleAuthManagerUser
from fastapi.testclient import TestClient

API_PATHS = {
    "public": "/api/v2",
    "ui": "/ui",
}

BASE_URL = "http://testserver"


def get_api_path(request):
    """Determine the API path based on the test's subdirectory."""
    test_dir = os.path.dirname(request.path)
    subdirectory_name = test_dir.split("/")[-1]

    return API_PATHS.get(subdirectory_name, "/")


@pytest.fixture
def test_client(request, caplog):
    from airflow.utils.db import initdb

    os.environ["AIRFLOW__DATABASE__EXTERNAL_DB_MANAGERS"] = (
        "astronomer.airflow.version_check.models.manager.VersionCheckDBManager"
    )
    os.environ["AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS"] = "True"

    # initialize the database
    initdb()
    app = create_app()
    auth_manager = app.state.auth_manager
    # set time_very_before to 2014-01-01 00:00:00 and time_very_after to tomorrow
    # to make the JWT token always valid for all test cases with time_machine
    time_very_before = datetime.datetime(2014, 1, 1, 0, 0, 0)
    time_after = datetime.datetime.now() + datetime.timedelta(days=1)
    with time_machine.travel(time_very_before, tick=False):
        token = auth_manager._get_token_signer(
            expiration_time_in_seconds=(time_after - time_very_before).total_seconds()
        ).generate(
            auth_manager.serialize_user(SimpleAuthManagerUser(username="test", role="admin")),
        )
    yield TestClient(app, headers={"Authorization": f"Bearer {token}"}, base_url=f"{BASE_URL}{get_api_path(request)}")


@pytest.fixture
def unauthorized_test_client(request):
    app = create_app()
    auth_manager = app.state.auth_manager
    token = auth_manager._get_token_signer().generate(
        auth_manager.serialize_user(SimpleAuthManagerUser(username="dummy", role=None))
    )
    yield TestClient(app, headers={"Authorization": f"Bearer {token}"}, base_url=f"{BASE_URL}{get_api_path(request)}")


@pytest.fixture
def session():
    from airflow.utils.session import create_session

    with create_session() as session:
        yield session
        session.rollback()
