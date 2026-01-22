#!/usr/bin/env python3
"""Script to lint and type-check version check UI files for pre-commit hook."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
WWW_DIR = PROJECT_ROOT / "astronomer" / "airflow" / "version_check" / "www"


def run_command(cmd: list[str], cwd: Path) -> None:
    """Run a command and exit if it fails."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout, file=sys.stdout)
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)


if __name__ == "__main__":
    original_files = sys.argv[1:] if len(sys.argv) > 1 else []
    print("Original files:", original_files)

    www_relative = WWW_DIR.relative_to(PROJECT_ROOT)
    files = [
        str(Path(file).relative_to(www_relative))
        for file in original_files
        if Path(file).is_relative_to(www_relative)
        and not file.endswith(".yaml")
        and "node_modules" not in file
        and ".pnpm-store" not in file
    ]

    all_non_yaml_files = [file for file in files if not file.endswith(".yaml")]
    print("All non-YAML files:", all_non_yaml_files)
    all_ts_files = [file for file in files if file.endswith(".ts") or file.endswith(".tsx")]
    print("All TypeScript files:", all_ts_files)

    run_command(["pnpm", "config", "set", "store-dir", ".pnpm-store"], cwd=WWW_DIR)
    run_command(
        ["pnpm", "install", "--frozen-lockfile", "--config.confirmModulesPurge=false"],
        cwd=WWW_DIR,
    )

    if all_non_yaml_files:
        run_command(["pnpm", "exec", "eslint", "--quiet", *all_non_yaml_files], cwd=WWW_DIR)
    else:
        run_command(["pnpm", "exec", "eslint", "--quiet", "."], cwd=WWW_DIR)

    run_command(["pnpm", "exec", "tsc", "--p", "tsconfig.app.json"], cwd=WWW_DIR)
