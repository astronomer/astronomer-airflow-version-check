# astronomer-airflow-version-check

An Apache Airflow plugin that will periodically (default, once per day) check
if there is a new version of Astronomer's Astro Runtime and display a
message in the Airflow UI

## Settings

This plugin looks at the following settings under the `astronomer` section of
the Airflow config. The easiest way of setting this is via environment
variables prefixed with `AIRFLOW__ASTRONOMER__`

- `update_check_interval`

  Number of seconds between each update check. Default 86400 (one day). Set to
  0 to disable update checks

- `update_check_timeout`

  HTTP timeout for requesting update document. Default 60

- `update_url`

  URL to request to find out about more udpates. Default to `updates.astronomer.io`
