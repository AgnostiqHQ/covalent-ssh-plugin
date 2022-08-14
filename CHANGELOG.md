# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [UNRELEASED]

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
