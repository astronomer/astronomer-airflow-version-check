# astronomer-airflow-version-check

An Apache Airflow plugin that will periodically (default, once per day) check
if there is a new version of Astronomer's Astro Runtime and display a
message in the Airflow UI.

Additionally, this plugin provides warnings in the Airflow UI for the following scenarios:
- When the current version will reach its End of Maintenance (EOM) in 30 days (default, configurable).
- When the current version has already reached its End of Maintenance (EOM).
- When the current version will reach its End of Basic Support (EOBS) in 30 days (default, configurable).
- When the current version has already reached its End of Basic Support (EOBS).
- When the current version has been yanked.

This plugin also shows options to dismiss the EOM and EOBS warnings for a configurable number of days (default is 7 days). There is also an option to completely disable these warnings.

Additionally, it checks if the current running version of Astronomer Runtime has been yanked. If a yanked version is detected, a warning message will appear in the Airflow UI. The yanked versions will not be displayed as available updates to prevent users from being prompted to upgrade to a yanked version.

## Warning Priority

When multiple warnings are applicable, the plugin displays only the most critical one in the following priority order:

1. **Yanked** (highest priority) - Cannot be dismissed
2. **End of Basic Support (EOBS)** - Can be dismissed
3. **End of Maintenance (EOM)** - Can be dismissed

## Settings

This plugin looks at the following settings under the `astronomer` section of
the Airflow config. The easiest way of setting this is via environment
variables prefixed with `AIRFLOW__ASTRONOMER__`.

### Update Check Settings

- `update_check_interval`

  Number of seconds between each update check. Default 86400 (one day). Set to
  0 to disable update checks.

- `update_check_timeout`

  HTTP timeout for requesting update document. Default is 60.

- `update_url`

  URL to request to find out about more updates. Default to `updates.astronomer.io`.

### End of Maintenance (EOM) Warning Settings

- `eom_warning_opt_out`

  Sets whether to opt out of End of Maintenance warnings. The default is `"False"`.

- `eom_dismissal_period_days`

  Sets the period for dismissing EOM warnings. The default is 7 days.

- `eom_warning_threshold_days`

  Sets the threshold (in days before EOM) for showing EOM warnings. The default is 30 days.

### End of Basic Support (EOBS) Warning Settings

- `eobs_warning_opt_out`

  Sets whether to opt out of End of Basic Support warnings. The default is `"False"`.

- `eobs_dismissal_period_days`

  Sets the period for dismissing EOBS warnings. The default is 7 days.

- `eobs_warning_threshold_days`

  Sets the threshold (in days before EOBS) for showing EOBS warnings. The default is 30 days.

## API Endpoints

This plugin provides a FastAPI-based API at `/version_check/`:

- `GET /version_check/ui/status` - Returns current version status and any active warnings
- `POST /version_check/ui/dismiss/eom` - Dismiss EOM warning for the configured period
- `POST /version_check/ui/dismiss/eobs` - Dismiss EOBS warning for the configured period

API documentation is available at `/version_check/docs` (Swagger UI) and `/version_check/redoc` (ReDoc).
