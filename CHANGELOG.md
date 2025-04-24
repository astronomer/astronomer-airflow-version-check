# Changelog

## Version 3.0.0
- Use new versioning scheme for checking of runtime images (#78)
- Move Version Check UI to runtime Middleware (#81)
- Remove FAB dependency (#82)

## Version 2.0.4
- Update README.md to replace AC reference with runtime reference (#64)
- Add warnings around current versions EOL date (#72)
- Add Warning for Yanked Runtime Versions (#74)

## Version 2.0.3
- Add has_access method to handle backward compatibility (#56)

## Version 2.0.2
- Hook at the `_execute` instead of run_scheduler_loop (#60)

## Version 2.0.1
- Properly set the version column type (#57)

## Version 2.0.0
- Use semantic versioning for checking of runtime images and remove deprecated AC supports (#54)

## Version 1.0.15
- Fix bug in ignoring new version available update banner (#50)
- Update the base template options (#51)

## Version 1.0.14
- Update plugin to work with 2.6.0 (#48)

## Version 1.0.13
- Catch SSLError & HTTPError during requests.get (#46)

## Version 1.0.12
- Fix Attribute error in lower versions of airflow (#43)

## Version 1.0.11
- Manually pre-install wheel so cryptography gets installed from a wheel (#33)
- Remove create table hook on upgradedb (#40)
- Make version check plugin work in runtime (#41)

## Version 1.0.10
- Fix plugin to work with Airflow 2.3.3+ (#37)
- Fix version compact (#38)

## Version 1.0.9

- Show available updates in a better way (#34)
- Add pre-commit (#35)
- Repeat 'venv' creation in publish job (#32)
- Fix setuptools not found during publish (#31)
- Bump CI dependencies (#28)

## Version 1.0.8

Released 2022-01-24

- Use `add_view_no_menu since add_api` is removed in airflow (#24)
- Fix CI issues and Bump dev requirements (#26)

## Version 1.0.7

Released 2020-12-17

- Fix issue with Session being closed (#23)

## Version 1.0.6

Released 2020-12-14

- Fix disabling update_check_interval checks (#21)
- Replace 2.0 Appbuilder base template (#22)

## Version 1.0.5

Released 2020-10-15

- Make the version check plugin Airflow 2.0 compatible (#17)
- Pin attrs to less tha 20.0 (#19)
- Skip creating table & spawning thread if `update_check_interval=0` (#18)

## Version 1.0.4

Released 2020-08-04

- Add more data to UserAgent on Updater Service requests (#15)

## Version 1.0.3

Released 2020-07-27

- Make the plugin MySQL compatible (#16)

## Version 1.0.2

Released 2020-07-25

- Stop showing notice if the current AC Version is already latest (#14)

## Version 1.0.1

- Don't stop airflow running when plugin's DB tables haven't been created (#1)

## Version 1.0.0

Released 2020-04-16

- Initial release
