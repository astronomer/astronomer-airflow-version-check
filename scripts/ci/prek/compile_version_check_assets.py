#!/usr/bin/env python3
"""Script to compile version check UI assets for pre-commit hook."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
WWW_DIR = PROJECT_ROOT / "astronomer" / "airflow" / "version_check" / "www"


def compile_assets():
    """Compile UI assets."""
    env = os.environ.copy()
    env["FORCE_COLOR"] = "true"

    print("### Installing pnpm dependencies ###")
    subprocess.check_call(
        ["pnpm", "install", "--frozen-lockfile", "--config.confirmModulesPurge=false"],
        cwd=os.fspath(WWW_DIR),
        env=env,
    )

    print("### Building assets ###")
    subprocess.check_call(
        ["pnpm", "run", "build"],
        cwd=os.fspath(WWW_DIR),
        env=env,
    )

    print("Assets compiled successfully.")


if __name__ == "__main__":
    compile_assets()
