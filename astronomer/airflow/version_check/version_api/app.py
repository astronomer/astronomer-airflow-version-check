from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from astronomer.airflow.version_check import plugin
from astronomer.airflow.version_check.version_api.routes import ui_router

PACKAGE_DIR = Path(__file__).parents[1]


def create_version_check_api_app() -> FastAPI:
    """Create FastAPI app for version check API."""
    app = FastAPI(
        title="Astronomer Version Check API",
        description=(
            "API for Astronomer Runtime version checking. Provides endpoints for "
            "checking version status, warnings (End of Maintenance, End of Basic Support, Yanked), "
            "and dismissing warnings."
        ),
        version=plugin.__version__,
    )

    app.include_router(ui_router, prefix="/ui")

    if ".cjs" not in mimetypes.suffix_map:
        mimetypes.add_type("application/javascript", ".cjs")

    www_dist = PACKAGE_DIR / "www" / "dist"
    if www_dist.exists():
        app.mount(
            "/static",
            StaticFiles(directory=www_dist.absolute(), html=True),
            name="version_check_static_files",
        )

    www_res = PACKAGE_DIR / "www" / "src" / "res"
    if www_res.exists():
        app.mount(
            "/res",
            StaticFiles(directory=www_res.absolute(), html=True),
            name="version_check_res_files",
        )

    return app
