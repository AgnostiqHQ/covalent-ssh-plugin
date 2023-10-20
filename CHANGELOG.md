# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [UNRELEASED]

### Changed

- Improved connection retry logic

## [0.22.0] - 2023-09-20

### Changed

- Updated license to Apache

## [0.21.0] - 2023-06-02

### Added

- Ability to specify a `remote_workdir` along with `create_unique_workdir` option for each electron / node.

## [0.20.0] - 2022-12-15

### Changed

- Removed references to `.env` file in the functional test README.

## [0.19.0] - 2022-12-06

### Changed

- Using executor aliases instead of classes for functional tests

## [0.18.0] - 2022-12-05

### Changed

- Functional tests using pytest and .env file configuration

## [0.17.0] - 2022-10-28

### Changed

- Constraining covalent version to be less than major version 1

## [0.16.0] - 2022-10-27

### Changed

- Fix errors in `license.yml`
- Added Alejandro to paul blart group

## [0.15.0] - 2022-10-25

### Changed

- Updated covalent version to `>=0.202.0`
- Removed redundant install steps from workflow

### Operations

- Updating pre-commit hooks version number.
- Added license workflow
- Pre-commit autoupdate.

## [0.14.0] - 2022-09-20

### Changed

- Renaming `credentials_file` to `ssh_key_file` to not have name conflict with key referring to cloud credential files

## [0.13.1] - 2022-09-20

### Fixed

- Fixed get_status to correctly assert if remote result file exists

## [0.13.0] - 2022-09-15


### Changed

- Updated requirements.txt to pin covalent to version 0.177.0.post1.dev0

### Tests

- Fixed config manager related test which broke as a result of changes in covalent

## [0.12.0] - 2022-09-13

### Changed

- Using covalent on `develop` rather than the stable version
- Using `RemoteExecutor` now instead of `BaseAsyncExecutor`
- Renamed `ssh_key_file` to `credentials_file` which is passed to the super class instead

### Added

- Implementation of abstract functions added to adhere to the `RemoteExecutor`'s template

## [0.11.0] - 2022-09-06

### Changed

- Changed python_path arg to conda_env in executor init for functional tests

## [0.10.0] - 2022-08-31

### Added

- Added basic functional test for CI

## [0.9.0] - 2022-08-29

### Changed

- Added conda bash hooks in order to activate environments properly in non-interactive sessions

### Tests

- Enabled Codecov

## [0.8.0] - 2022-08-22

### Added

- Added basic functional test for CI

### Added

- Added back `_EXECUTOR_PLUGIN_DEFAULTS` to ssh plugin

## [0.7.0] - 2022-08-19

### Changed

- `python3_path` has been changed to `python_path`
- `ssh_key_file` is now a required parameter
- Default `python_path` value is now `python`
- `cache_dir` default simplified and relies on `get_config("dispatcher.cache_dir")` now
- `cache_dir` and `ssh_key_file` now support relative paths, they get converted to abs internally automatically
- Appropriately changed variable names

### Added

- `SSHExecutor` is now importable from `covalent_ssh_plugin`
- `conda_env` parameter added which can be used to execute the function in a separate conda environment on the remote machine
- Added `do_cleanup` (`True` by default) parameter to allow cleanup of various files created locally, and on remote machine
- Added more logging statements for better debugging
- Added `*.ipynb` files to `.gitignore` for easier experimentation

### Fixed

- Fixed reference of `remote_dir` to `remote_cache_dir` in `README.md`

### Tests

- Updated tests to reflect above changes

## [0.6.1] - 2022-08-19

### Fixed

- Added additional logging and explicit SSH close connection call to avoid wait_closed() call from hanging

## [0.6.0] - 2022-08-18

### Changed

- Update `covalent` version to `stable`

## [0.5.1] - 2022-08-14

### Fixed

- Fixed release trigger

## [0.5.0] - 2022-08-14

### Changed

- Changed the readme banner

## [0.4.0] - 2022-08-04

### Changed

- Switched to asynchronous SSH connections making the executor async-aware.
- Tests have been updated to reflect the switch to async ssh connections.

## [0.3.0] - 2022-05-26

### Changed

- New logo to reflect revamp in UI.
- Backport some changes

### Fixed

- Handle exceptions correctly.
- Fix return type when ssh connection fails.
- Fix tests

## [0.2.2] - 2022-05-26

### Fixed

- Fixed validating package tarball
- Updated running tests via pytests

## [0.2.1] - 2022-04-26

### Added

- Unit tests written and added to the .github workflows.

## [0.2.0] - 2022-04-16

### Changed

- Small refactor to align with the Covalent micro-services refactor.

## [0.1.0] - 2022-04-08

### Changed

- Changed global variable executor_plugin_name -> EXECUTOR_PLUGIN_NAME in executors to conform with PEP8.

## [0.0.1] - 2022-03-11

### Added

- Core files for this repo.
- CHANGELOG.md to track changes (this file).
- Semantic versioning in VERSION.
- CI pipeline job to enforce versioning.
