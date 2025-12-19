import functools
import getpass
import operator
import os
import pathlib
import pprint
import re
import tempfile
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml import YAMLError
from typeguard import typechecked

from pcvs import io
from pcvs import PATH_INSTDIR
from pcvs import testing
from pcvs.backend.metaconfig import GlobalConfig
from pcvs.converter import yaml_converter
from pcvs.helpers.exceptions import TestException
from pcvs.helpers.exceptions import ValidationException
from pcvs.helpers.validation import ValidationScheme
from pcvs.plugins import Plugin
from pcvs.testing import tedesc
from pcvs.testing.test import Test

# pylint for python3.10 and pylint for python3.12 does not agree on if this should be snake case or upper case ...
constant_tokens: dict | None = None  # pylint: disable=invalid-name


@typechecked
def init_constant_tokens() -> None:
    """
    Initialize global tokens to be replaced.

    The dict is built from profile specifications. The exact location for this
    function is still to be determined.
    """
    global constant_tokens
    constant_tokens = {
        "@HOME@": str(pathlib.Path.home()),
        "@USER@": getpass.getuser(),
    }
    for comp, comp_node in GlobalConfig.root.get("compiler", {}).get("compilers", {}).items():
        constant_tokens[f"@COMPILER_{comp.upper()}@"] = comp_node.get("program", "")

    constant_tokens["@RUNTIME_PROGRAM@"] = GlobalConfig.root.get("runtime", {}).get("program", "")


@typechecked
def replace_special_token(content: str, src: str, build: str, prefix: str | None) -> str:
    output = []
    errors = []

    global constant_tokens
    if constant_tokens is None:
        init_constant_tokens()

    if prefix is None:
        prefix = ""

    assert constant_tokens is not None
    tokens = {
        **constant_tokens,
        "@BUILDPATH@": os.path.join(build, prefix),
        "@SRCPATH@": os.path.join(src, prefix),
        "@ROOTPATH@": src,
        "@BROOTPATH@": build,
        "@SPACKPATH@": "TBD",
    }

    r = re.compile("(?P<name>@[a-zA-Z0-9-_]+@)")
    for line in content.split("\n"):
        for match in r.finditer(line):

            name = match.group("name")
            if name not in tokens:
                errors.append(name)
            else:
                line = line.replace(name, tokens[name])
        output.append(line)

    if errors:
        raise ValidationException.WrongTokenError(invalid_tokens=str(errors))
    return "\n".join(output)


@typechecked
class TestFile:
    """
    A TestFile manipulates source files to be processed as benchmarks
    (pcvs.yml & pcvs.setup).

    It handles global information about source imports & building one execution
    script (``list_of_tests.sh``) per input file.

    :ivar _in: YAML input file
    :vartype _in: str
    :ivar _path_out: prefix where to store output artifacts
    :vartype _path_out: str
    :ivar _raw: stream to populate the TestFile (rather than opening input file)
    :vartype _raw: dict
    :ivar _label: label the test file comes from
    :vartype _label: str
    :ivar _prefix: subtree the test file has been extracted
    :vartype _prefix: str
    :ivar _tests: list of tests handled by this file
    :vartype _tests: list
    :ivar _debug: debug instructions (concatenation of TE debug infos)
    :vartype _debug: dict
    """

    cc_pm_string = ""
    rt_pm_string = ""
    val_scheme_cache = None

    def __init__(
        self,
        file_in: str,
        path_out: str,
        data: dict[str, Any] | None = None,
        label: str | None = None,
        prefix: str | None = None,
    ):
        """
        Constructor method.

        :param file_in: input file
        :param path_out: prefix to store artifacts
        :param data: raw data to inject instead of opening input file
        :param label: label the TE is coming from
        :param prefix: testfile Subtree (may be Nonetype)
        """
        self._in: str = file_in
        self._path_out: str = path_out
        self._raw: dict[str, Any] | None = data
        self._label: str | None = label
        self._prefix: str | None = prefix
        self._tests: list[Test] = []
        self._debug: dict = {}

        if TestFile.val_scheme_cache is None:
            TestFile.val_scheme_cache = ValidationScheme("te")
        self.val_scheme: ValidationScheme = TestFile.val_scheme_cache

    def load_from_file(self, f: str | None = None) -> None:
        if f is None:
            f = self._in
        else:
            self._in = f
        with open(f, "r") as fh:
            stream = fh.read()
            self.load_from_str(stream)

    def load_from_str(self, data: str) -> None:
        """
        Fill a File object from stream.

        This allows reusability (by loading only once).

        :param data: the YAML-formatted input stream.
        """
        assert self._label is not None and self._prefix is not None
        source, _, build, _ = testing.test.generate_local_variables(self._label, self._prefix)

        stream = replace_special_token(data, source, build, self._prefix)
        try:
            self._raw = YAML(typ="safe").load(stream)
        except YAMLError as ye:
            raise ValidationException.YamlError(file=self._in, content=stream) from ye

    def save_yaml(self) -> None:
        assert self._label is not None and self._prefix is not None
        _, _, _, curbuild = testing.test.generate_local_variables(self._label, self._prefix)

        with open(os.path.join(curbuild, "pcvs.setup.yml"), "w") as fh:
            YAML(typ="safe").dump(self._raw, fh)

    @io.capture_exception(Exception, doexit=False)
    def validate(self, allow_conversion: bool = True) -> bool:
        """Test file validation"""
        try:
            if self._raw:
                self.val_scheme.validate(self._raw, filepath=self._in)
            return True
        except ValidationException.WrongTokenError as e:
            # Issues with replacing @...@ keys
            e.add_dbg("file", self._in)
            raise TestException.TestExpressionError([self._in]) from e

        except ValidationException.FormatError as e:
            # YAML is valid but not following the Scheme
            # If YAML is invalid, load() functions will failed first

            # At first attempt, YAML are converted.
            # There is no second chance
            if not allow_conversion:
                e.add_dbg("file", self._in)
                raise e

            tmpfile = tempfile.mkstemp()[1]
            with open(tmpfile, "w", encoding="utf-8") as fh:
                YAML(typ="safe").dump(self._raw, fh)

            try:
                template = os.path.join(PATH_INSTDIR, "templates/config/group-compat.yml")
                yaml_converter.convert(tmpfile, "te", template, None, None, False, True, True)
            except Exception as er:
                io.console.error(f"An error occurred when trying to update file {self._in}.")
                raise er from e

            with open(tmpfile, "r", encoding="utf-8") as fh:
                converted_data = YAML(typ="safe").load(fh)

            self._raw = converted_data
            # I don't understand this type error
            self.validate(allow_conversion=False)  # type: ignore
            io.console.warning("\t--> Legacy syntax for: {}".format(self._in))
            io.console.warning("Please consider updating it with `pcvs_convert -k te`")
            return False

    @property
    def nb_descs(self) -> int:
        """Number of tests descriptor in the testfile."""
        if self._raw is None:
            return 0
        return len(self._raw.keys())

    @property
    def nb_tests(self) -> int:
        """Number of tests in the testfile."""
        if self._tests is None:
            return 0
        return len(self._tests)

    @property
    def tests(self) -> list[Test]:
        """The tests object once generated."""
        return self._tests

    @property
    def raw_yaml(self) -> dict[str, Any]:
        """Return raw yaml from TestFile."""
        assert self._raw is not None
        return self._raw

    def process(self) -> None:
        """Load the YAML file and map YAML nodes to Test()."""
        # _, _, _, _ = testing.test.generate_local_variables(
        #     self._label, self._prefix)

        # if file hasn't be loaded yet
        # if self._raw is None:
        #     self.load_from_file(self._in)

        self.validate()

        # main loop, parse each node to register tests
        assert self._raw is not None
        assert self._label is not None and self._prefix is not None
        for k, content in self._raw.items():
            GlobalConfig.root.get_internal("pColl").invoke_plugins(Plugin.Step.TDESC_BEFORE)
            if content is None:
                # skip empty nodes
                continue
            td = tedesc.TEDescriptor(k, content, self._label, self._prefix)
            for test in td.construct_tests():
                self._tests.append(test)
            io.console.crit_debug(
                "Test descriptor: {}: {}".format(td.name, pprint.pformat(td.get_debug()))
            )

            GlobalConfig.root.get_internal("pColl").invoke_plugins(Plugin.Step.TDESC_AFTER)

            # register debug information relative to the loaded TEs
            self._debug[k] = td.get_debug()

    def flush_sh_file(self) -> None:
        """Store the given input file into their destination."""
        fn_sh = os.path.join(self._path_out, "list_of_tests.sh")
        cobj = GlobalConfig.root.get_internal("cc_pm")
        if TestFile.cc_pm_string == "" and cobj:
            TestFile.cc_pm_string = "\n".join([e.get(load=True, install=False) for e in cobj])

        robj = GlobalConfig.root.get_internal("rt_pm")
        if TestFile.rt_pm_string == "" and robj:
            TestFile.rt_pm_string = "\n".join([e.get(load=True, install=False) for e in robj])

        with open(fn_sh, "w") as fh_sh:
            fh_sh.write(
                """#!/bin/sh
if test -n "{simulated}"; then
    PCVS_SHOW=1
    PCVS_SHOW_ENV=1
    PCVS_SHOW_MOD=1
    PCVS_SHOW_CMD=1
fi

if test -z "$PCVS_SHOW"; then
eval "{pm_string}"
elif test -n "$PCVS_SHOW_MOD"; then
test -n "$PCVS_VERBOSE" && echo "## MODULE LOADED FROM PROFILE ##"
cat<<EOF
{pm_string}
EOF
#else... SHOW but not this option --> nothing to do

fi

for arg in "$@"; do case $arg in
""".format(
                    simulated=(
                        "sim" if GlobalConfig.root["validation"].get("simulated", False) else ""
                    ),
                    pm_string="\n".join([TestFile.cc_pm_string, TestFile.rt_pm_string]),
                )
            )

            for test in self._tests:
                fh_sh.write(test.generate_script(fn_sh))
                # GlobalConfig.root.get_internal("orchestrator").add_new_job(test)

            fh_sh.write(
                """
        --list) printf "{list_of_tests}\\n"; exit 0;;
        *) printf "Invalid test-name \'$arg\'\\n"; exit 1;;
        esac
    done

    if test -z "$PCVS_SHOW"; then
        eval "${{pcvs_load}}" || exit "$?"
        eval "${{pcvs_env}}" || exit "$?"
        eval "${{pcvs_cmd}}" || exit "$?"
        exit $?
    else
        if test -n "$PCVS_SHOW_MOD"; then
            test -n "$PCVS_VERBOSE" && echo "#### MODULE LOADED ####"
cat<<EOF
${{pcvs_load}}
EOF
        fi

        if test -n "$PCVS_SHOW_ENV"; then
        test -n "$PCVS_VERBOSE" && echo "###### SETUP ENV ######"
cat<<EOF
${{pcvs_env}}
EOF
        fi
        if test -n "$PCVS_SHOW_CMD"; then
        test -n "$PCVS_VERBOSE" && echo "##### RUN COMMAND #####"
cat<<EOF
${{pcvs_cmd}}
EOF
        fi
    fi
    exit $?\n""".format(
                    list_of_tests="\n".join([t.name for t in self._tests])
                )
            )

        self.generate_debug_info()

    def generate_debug_info(self) -> None:
        """Dump debug info to the appropriate file for the input object."""
        if len(self._debug) and io.console.verb_debug:
            with open(os.path.join(self._path_out, "dbg-pcvs.yml"), "w") as fh:
                # compute max number of combinations from system iterators
                sys_cnt = functools.reduce(
                    operator.mul,
                    [len(v["values"]) for v in GlobalConfig.root["criterion"].values()],
                )
                self._debug.setdefault(".system-values", {})
                self._debug[".system-values"].setdefault("stats", {})

                for c_k, c_v in GlobalConfig.root["criterion"].items():
                    self._debug[".system-values"][c_k] = c_v["values"]
                self._debug[".system-values"]["stats"]["theoric"] = sys_cnt
                yml = YAML(typ="safe")
                yml.default_flow_style = None
                yml.dump(self._debug, fh)
