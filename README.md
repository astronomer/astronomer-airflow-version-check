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

  **Example:** If `eom_warning_threshold_days = 30`, the warning will start appearing when there are 30 days or fewer remaining until the End of Maintenance date.

### End of Basic Support (EOBS) Warning Settings

- `eobs_warning_opt_out`

  Sets whether to opt out of End of Basic Support warnings. The default is `"False"`.

- `eobs_dismissal_period_days`

  Sets the period for dismissing EOBS warnings. The default is 7 days.

- `eobs_warning_threshold_days`

  Sets the threshold (in days before EOBS) for showing EOBS warnings. The default is 30 days.

  **Example:** If `eobs_warning_threshold_days = 30`, the warning will start appearing when there are 30 days or fewer remaining until the End of Basic Support date.

## Understanding Warning Threshold vs Dismissal Period

The difference between **warning threshold days** and **dismissal period days**:

- **Warning Threshold Days** (`eom_warning_threshold_days`, `eobs_warning_threshold_days`):
  - Determines **when** to start showing the warning
  - Default: 30 days
  - Example: If `eom_warning_threshold_days = 30`, the warning appears when there are 30 days or fewer until the End of Maintenance date

- **Dismissal Period Days** (`eom_dismissal_period_days`, `eobs_dismissal_period_days`):
  - Determines **how long** the warning stays hidden after a user dismisses it
  - Default: 7 days
  - Example: If `eom_dismissal_period_days = 7`, when a user dismisses the warning, it won't show again for 7 days

** Example for understanding:**
- `eom_warning_threshold_days = 30`: Warning starts appearing 30 days before the End of Maintenance date
- `eom_dismissal_period_days = 7`: When dismissed, the warning stays hidden for 7 days

So if EOM is on January 31st and today is January 1st:
- The warning appears (30 days remaining ≤ threshold)
- User dismisses it on January 1st
- Warning is hidden until January 8th (7 days later)
- Warning reappears on January 8th if still within the threshold period

## API Endpoints

This plugin provides a FastAPI-based API at `/version_check/`:

- `GET /version_check/status` - Returns current version status and any active warnings
- `POST /version_check/dismiss/eom` - Dismiss EOM warning for the configured period
- `POST /version_check/dismiss/eobs` - Dismiss EOBS warning for the configured period

API documentation is available at `/version_check/docs` (Swagger UI) and `/version_check/redoc` (ReDoc).

## Building and Packaging

Before building the Python package, you must build the UI assets. The packaging process expects the built assets to be available in `astronomer/airflow/version_check/www/dist/`.

**Important:** There is currently no automatic step in the packaging process to build the UI assets. You must manually run the build commands before creating the wheel:

```bash
cd astronomer/airflow/version_check/www
pnpm install
pnpm build
```

After building the UI assets, you can build the Python package:

```bash
python setup.py sdist bdist_wheel
```

The built assets will be included in the final wheel package.
