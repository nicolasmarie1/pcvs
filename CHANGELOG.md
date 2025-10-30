# CHANGELOG

All major changes to PCVS are documented here. Additional sections will help to
track what changed from each release.

The format is based on [Keep a Changelog](https://keepachangelog.com/)

## [0.8.0] -- 2025-11-3

### Added

- CLI: Add `--run-filter` to filter jobs to run based on tags
- CLI: Add `--print-filter` to filter jobs to print output based on tags
- CLI: Add `graph` command to output graph formatted metrics about a bank (success rate, tests duration...)
- CLI: Add `--profile-path` to specify the profile to use as a path
- DOC: Build and deploy documentation
- Jobs: Support compilers wrapper
- Jobs: Add a one hour global timeout
- Jobs: Add `lang` key to specify explicitly the language of the test
- Jobs: Add separated `validation` node to build section of the test descriptors -> Build tests can validated in the same way as run tests
- Jobs: Add `local` option to test descriptors criterions -> When turned to `false`, the Criterion is applied to the wrapper instead of to the program
- Report: Add TUI to visualize results in terminal (with `--tui` option)

### Changed

- Profile: Change compilers definition to help with adding new compilers (**Breaking change**)
- CLI: Add summary table at the end of runs even with verbosity opt in
- DOC: Disable documentation generation by default
- Errors: Changed most warnings
- Jobs: Improve plugin integration in the orchestrator
- Jobs: Remove mandatory base64 plugin encoding (plugins can be written in pure python)
- Jobs: Split timeout in hard_timeout (old behavior: job is killed) and soft_timeout (test is marked timeout but continue until completion)
- Profile: Add defaultplugin key to specify a default plugin instead of copy pasting
- Session: Avoid lock contention by using a one file per session structure

### Removed

- Jobs: Remove timeout from compilation tests
- Jobs: Remove expect_exit validation propagated to compilation tests

### Fixed

- Bank: Fix internal issues
- Installation: Fix race condition when creating PCVS home directory
- Jobs: Fix environment export
- Jobs: Fix analysis validation based on previous runs in the bank
- Jobs: Fix analysis validation when bank is disabled
- Jobs: Fix environment propagation for Make, AutoTools and CMake build systems
- Profile: Fix default plugin overriding user plugin
- Profile: Add information on wrong configuration
- Orchestrator: Fix scheduler pruning by removing the maximum attempts discard
- Orchestrator: Fix tests being queue before their dependencies
- Orchestrator: Fix deadlock on last job being an ERR_DEP
- Orchestrator: Fix deadlock on last job with wrong resources allocation
- Orchestrator: Fix PCVS aborting its children processes on SIGTERM (ctrl+c)
- Report: (Webview) Add 404 error
- Scan: Fix file finding

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

- **YAML**: New syntax for describing tests and configurations (**breaking change**)
- **ARCHIVE**: New format (**breaking change**)
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
