#!/usr/bin/env python3
"""Script to compile version check UI assets for pre-commit hook."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
WWW_DIR = PROJECT_ROOT / "astronomer" / "airflow" / "version_check" / "www"
DIST_DIR = WWW_DIR / "dist"
HASH_FILE = PROJECT_ROOT / "www-hash.txt"

SKIP_PATH_REGEXPS = [
    ".*/node_modules.*",
    ".*/.pnpm-store.*",
    ".*/dist.*",
    ".*/package-lock.json$",
    ".*/pnpm-lock.yaml$",
]


def get_directory_hash(directory: Path, skip_path_regexps: list[str]) -> str:
    """Calculate hash of directory contents, skipping specified paths."""
    files = sorted(directory.rglob("*"))
    for skip_path_regexp in skip_path_regexps:
        matcher = re.compile(skip_path_regexp)
        files = [file for file in files if not matcher.match(os.fspath(file.resolve()))]
    sha = hashlib.sha256()
    for file in files:
        if file.is_file() and not file.name.startswith("."):
            sha.update(file.read_bytes())
    return sha.hexdigest()


def compile_assets():
    """Compile UI assets if the source directory has changed."""
    HASH_FILE.parent.mkdir(exist_ok=True, parents=True)

    if DIST_DIR.exists():
        old_hash = HASH_FILE.read_text().strip() if HASH_FILE.exists() else ""
        new_hash = get_directory_hash(WWW_DIR, skip_path_regexps=SKIP_PATH_REGEXPS)
        if new_hash == old_hash:
            print(f"The '{WWW_DIR}' directory has not changed! Skip regeneration.")
            return
        print(f"The directory has changed, regenerating assets in {WWW_DIR}.")
        print("Old hash: " + old_hash)
        print("New hash: " + new_hash)
    else:
        shutil.rmtree(DIST_DIR, ignore_errors=True)

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

    new_hash = get_directory_hash(WWW_DIR, skip_path_regexps=SKIP_PATH_REGEXPS)
    HASH_FILE.write_text(new_hash + "\n")
    print(f"Assets compiled successfully. New hash: {new_hash}")


if __name__ == "__main__":
    compile_assets()
