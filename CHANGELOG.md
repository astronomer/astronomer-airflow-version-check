# Changelog

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
