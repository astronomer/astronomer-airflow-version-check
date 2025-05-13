from __future__ import annotations

from pathlib import Path

from airflow import settings
from airflow.exceptions import AirflowException
from astronomer.airflow.version_check.models.db import metadata
from airflow.utils.db import _offline_migration, print_happy_cat
from airflow.utils.db_manager import BaseDBManager

PACKAGE_DIR = Path(__file__).parents[1]

_REVISION_HEADS_MAP: dict[str, str] = {
    "3.1.0": "b5ad49d1f9b4",
}


class VersionCheckDBManager(BaseDBManager):
    """Manages Version Check database."""

    metadata = metadata
    version_table_name = "alembic_version_astro_version_check"
    migration_dir = (PACKAGE_DIR / "migrations").as_posix()
    alembic_file = (PACKAGE_DIR / "alembic.ini").as_posix()
    supports_table_dropping = True

    def create_db_from_orm(self):
        super().create_db_from_orm()

    def upgradedb(self, to_revision=None, from_revision=None, show_sql_only=False):
        """Upgrade the database."""
        if from_revision and not show_sql_only:
            raise AirflowException("`from_revision` only supported with `sql_only=True`.")

        # alembic adds significant import time, so we import it lazily
        if not settings.SQL_ALCHEMY_CONN:
            raise RuntimeError("The settings.SQL_ALCHEMY_CONN not set. This is a critical assertion.")
        from alembic import command

        config = self.get_alembic_config()

        if show_sql_only:
            if settings.engine.dialect.name == "sqlite":
                raise SystemExit("Offline migration not supported for SQLite.")
            if not from_revision:
                from_revision = self.get_current_revision()

            if not to_revision:
                script = self.get_script_object(config)
                to_revision = script.get_current_head()

            if to_revision == from_revision:
                print_happy_cat("No migrations to apply; nothing to do.")
                return
            _offline_migration(command.upgrade, config, f"{from_revision}:{to_revision}")
            return  # only running sql; our job is done

        command.upgrade(config, revision=to_revision or "heads")

    def downgrade(self, to_revision, from_revision=None, show_sql_only=False):
        if from_revision and not show_sql_only:
            raise ValueError(
                "`from_revision` can't be combined with `show_sql_only=False`. When actually "
                "applying a downgrade (instead of just generating sql), we always "
                "downgrade from current revision."
            )

        if not settings.SQL_ALCHEMY_CONN:
            raise RuntimeError("The settings.SQL_ALCHEMY_CONN not set.")

        # alembic adds significant import time, so we import it lazily
        from alembic import command

        self.log.info(
            "Attempting downgrade of Astronomer Version Check plugin migration to revision %s", to_revision
        )
        config = self.get_alembic_config()

        if show_sql_only:
            self.log.warning("Generating sql scripts for manual migration.")
            if not from_revision:
                from_revision = self.get_current_revision()
            if from_revision is None:
                self.log.info("No revision found")
                return
            revision_range = f"{from_revision}:{to_revision}"
            _offline_migration(command.downgrade, config=config, revision=revision_range)
        else:
            self.log.info("Applying Astronomer Version Check plugin downgrade migrations.")
            command.downgrade(config, revision=to_revision, sql=show_sql_only)

    def drop_tables(self, connection):
        super().drop_tables(connection)
