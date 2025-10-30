# CHANGELOG

All major changes to PCVS are documented here. Additional sections will help to
track what changed from each release.

The format is based on [Keep a Changelog](https://keepachangelog.com/)

## [0.6.0] -- 2022-09-16

### Added

- Examples: Add JUnit testings + Bot example
- CLI: Add support for partial names for `exec` command
- CLI: Add `--show` option to display direct output for `exec` command
- CLI: Add `--print` option to manage test verbosity
- Jobs: Add analysis method to validate a test
- Jobs: Add op support for criterion constraints
- Profile: Add templates for *gcc*, *icc* and *mpi-slurm*
- Profile: Add default plugin
- Report: (Webview) Add Failure-only section
- Report: Allow archive submission

### Changed

- Bank: Convert to Git API
- Jobs: Manggle names with criterion name if no subtitle provided

### Removed

- CLI: Open file with EDITOR option (`-e` or `--editor`)

### Fixed

- Orchestator: Discard tests with too many attempts (avoiding deadlocks)
- Report: (Webview) Fix broken links

## [0.5.0] -- 2021-11-16

### Added

- Initial release
- Bank, config & profile support
- Complete Python3.6+ rewrite
- *NEW* Orchestrator
- *NEW* Plugin architecture
- *NEW* Webview
