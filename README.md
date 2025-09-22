PCVS Documentation
==================

Parallel Computing Validation System (PCVS) is a Validation Orchestrator
designed by and for software at scale. Its primary target is HPC applications &
runtimes but can flawlessly address smaller use cases. PCVS can help users to
create their test scenarios and reuse them among multiples implementations, a
high value when it comes to validating Programmation standards (like APIs &
ABIs). No matter the number of programs, benchmarks, languages, or tech
non-regression bases use, PCVS gathers in a single execution, and, with a focus
on interacting with HPC batch managers efficiently, run jobs concurrently to
reduce the time-to-result overall. Through basic YAML-based configuration files,
PCVS handles more than hundreds of thousands of tests and helps developers to
ensure code production is moving forward.


## Quick installation guide

A more detailed guide to install PCVS can be found in the appropriate
documentation, here is a quick overview to set up and test the framework.

```bash
    # considering python3.7+
    $ pip3 install .
    # for dev/testing purposes, use:
    $ pip3 install '.[dev]'
    # basic tests:
    $ tox -e pcvs-coverage
    # OR
    $ coverage run
```

## Complete documentation

PCVS documentation is currently in active progress. Feel free to redistribute
comments and/or notes to the dev team about what should be more covered.
Multiple documentation can be generated from this repo:

* the CLI is managed and documented through ``click``. The manpages can be
  automatically built with the third-party tool ``click-man`` (not a dep,
  should be installed manually). Note that these manpages may not contain more
  information than the content of each ``--help`` command.
* The general documentation use ``sphinx`` and can be built by running
  ``make html`` in the docs directory.

## Authors

This work is currently supported by the French Alternative Energies and Atomic
Energy Commission (CEA). For any question and/or remarks, please contact :

*  Nicolas MARIE <nicolas.marie@uvsq.fr>

## Licensing

PCVS is released under the [CeCILL-C Free Software License.](https://cecill.info/licences/Licence_CeCILL-C_V1-en.txt).
