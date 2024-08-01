# astronomer-airflow-version-check

An Apache Airflow plugin that will periodically (default, once per day) check
if there is a new version of Astronomer's Astro Runtime and display a
message in the Airflow UI.

Additionally, this plugin provides warnings in the Airflow UI for the following scenarios:
- When the current version will reach its end of life (EOL) in 30 days (default, configurable).
- When the current version has already reached its end of life (EOL).
- When the current version has been yanked.

This plugin also shows options to dismiss the EOL warnings for a configurable number of days (default is 7 days). There is also an option to completely disable the EOL warning.

Additionally, it checks if the current running version of Astronomer Runtime has been yanked. If a yanked version is detected, a warning message will appear in the Airflow UI. Removed versions will not be displayed as available updates to prevent users from being prompted to upgrade to a yanked version.

## Settings

This plugin looks at the following settings under the `astronomer` section of
the Airflow config. The easiest way of setting this is via environment
variables prefixed with `AIRFLOW__ASTRONOMER__`.

- `update_check_interval`

  Number of seconds between each update check. Default 86400 (one day). Set to
  0 to disable update checks.

- `update_check_timeout`

  HTTP timeout for requesting update document. Default is 60.

- `update_url`

  URL to request to find out about more udpates. Default to `updates.astronomer.io`.

- `eol_warning_opt_out`

  Sets whether to opt out of EOL warnings. The default is `"False"`.

- `eol_dismissal_period_days`

  Sets the period for dismissing EOL warnings. The default is 7 days.

- `eol_warning_threshold_days`

  Sets the threshold for showing EOL warnings. The default is 30 days.
