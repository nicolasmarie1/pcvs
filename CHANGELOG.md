# CHANGELOG

All major changes to PCVS are documented here. Additional sections will help to
track what changed from each release.

The format is based on [Keep a Changelog](https://keepachangelog.com/)

## [0.7.0] -- 2023-06-9

### Added

- Bank: Store the config with the runs information
- Bank: Store automatically metadate after run
- Bank: Add `--message` option to tag on an entry
- CLI: Add `--successful` option to return a non-zero value if a test fails
- CLI: Add `remote-run` command
- Jobs: Add new build macro `@COMPILER_*@`
- Jobs: Integrate env/args propagation to any build system
- Jobs: Write the generated yaml from setup files
- Jobs: Handle the `None` special case
- Jobs: Raise exception on bad-formatted values for criterion
- Report: (Webview) Add configuration to main session page

### Changed

- **YAML**: New syntax for describing tests and configurations (breaking old yaml files)
- **ARCHIVE**: New format (breaking old archives)
- Check: Disable auto-conversion
- CLI: Change default values for options
- CLI: Avoid real run with `--show` for `exec` command
- CLI: Disable `--print` if `-v` is not provided
- Errors: Make them more explicit
- Orchestrator: Support parallelisation of jobs
- Orchestrator: Propagate autokill
- Profile: Save wrongly-formatted files (instead of rej\* files)
- Report: (Webview) Make elapsed time sortable

### Removed

- Bank: Remove per bank configuration
- Report: (Webview) paging -> all tests are displayed on a single page
- Report: (Webview) autorefresh

### Fixed

- Bank: Fix archive upload
- Check: Fix wrong setup computed path
- CLI: Fix `--print errors` verbosity to be compatible with Ruamel
- Jobs: Source custom environment in setup files
- Jobs: Fix return code propagation from setup files written in shell script
- Orchestrator: Fix signal propagation to interrupt deadlocked jobs
- Orchestrator: Fix job pickup selection
- Report: Rebuild view with missing information
- Report: Fix read access when extracting archive
- Session: Fix log redirection

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
