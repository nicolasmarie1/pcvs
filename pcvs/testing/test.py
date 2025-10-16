import base64
import hashlib
import json
import os
import re
import shlex
from enum import IntEnum

from pcvs import io
from pcvs.helpers.criterion import Combination
from pcvs.helpers.system import GlobalConfig
from pcvs.helpers.system import ValidationScheme
from pcvs.helpers.utils import Program
from pcvs.plugins import Plugin


class Test:
    r"""
    Smallest component of a validation process.

    A test is basically a shell command to run. Depending on its post-execution
    status, a success or a failure can be determined. To handle such component
    in a convenient way, more information can be attached to the command like a
    name, the elapsed time, the output, etc.

    In order to make test content flexible, there is no fixed list of
    attributes. A Test() constructor is initialized via (\*args, \*\*kwargs), to
    populate a dict `_array`.

    :cvar str NOSTART_STR: constant, setting default output when job cannot be run.
    """

    SCHED_MAX_ATTEMPTS = 50
    res_scheme = ValidationScheme("test-result")

    NOSTART_STR = b"This test cannot be started."
    MAXATTEMPTS_STR = b"This test has failed to be scheduled too many times. Discarded."

    class State(IntEnum):
        """Provide Status management, specifically for tests/jobs.

        Defined as an enum, it represents different states a job can take during
        its lifetime. As tests are then serialized into a JSON file, there is
        no need for construction/representation (as done for Session states).

        :var int WAITING: Job is currently waiting to be scheduled
        :var int IN_PROGRESS: A running Set() handle the job, and is scheduled
            for run.
        :var int EXECUTED: Job have been executed, but result status
            has not been computed yet.
        :var int SUCCESS: Job successfully run and passes all checks (rc,
            matchers...)
        :var int FAILURE: Job didn't succeed, at least one condition failed.
        :var SOFT_TIMEOUT: Job has exceeded his soft time limit but pass.
        :var HARD_TIMEOUT: Job has exceeded his hard time limit and got killed.
        :var int ERR_DEP: Special cases to manage jobs descheduled because at
            least one of its dependencies have failed to complete.
        :var int ERR_OTHER: Any other uncaught situation.
        """

        WAITING = 0
        IN_PROGRESS = 1
        EXECUTED = 2
        SUCCESS = 3
        FAILURE = 4
        SOFT_TIMEOUT = 5
        HARD_TIMEOUT = 6
        ERR_DEP = 7
        ERR_OTHER = 8

        def __str__(self):
            """Stringify to return the label.

            :return: the enum name
            :rtype: str
            """
            return self.name

        def __repr__(self):
            """Enum representation a tuple (name, value).

            :return: a tuple mapping the enum.
            :rtype: tuple
            """
            return "({}, {})".format(self.name, self.value)

    BAD_STATES = [
        State.ERR_DEP,
        State.ERR_OTHER,
        State.FAILURE,
        State.HARD_TIMEOUT,
    ]

    ALL_STATES = [
        State.SUCCESS,
        State.FAILURE,
        State.ERR_DEP,
        State.HARD_TIMEOUT,
        State.SOFT_TIMEOUT,
        State.ERR_OTHER,
    ]

    def __init__(self, **kwargs):
        """constructor method.

        :param kwargs: flexible list of arguments to initialize a Test with.
        :type kwargs: dict
        """
        self._rc = 0
        self._comb = kwargs.get("comb")
        self._cwd = kwargs.get("wd")
        self._exectime = 0.0
        self._output = b""
        self._state = Test.State.WAITING
        cores_per_nodes = GlobalConfig.root.get("machine", {}).get("cores_per_nodes", 1)
        self._resources: list[int] = kwargs.get("resources", [1, cores_per_nodes])
        for r in self._resources:
            assert r is not None

        self._testenv = kwargs.get("environment")
        self._id = {
            "te_name": kwargs.get("te_name", "noname"),
            "label": kwargs.get("label", "nolabel"),
            "subtree": kwargs.get("subtree", "nosubtree"),
            "comb": self._comb.get_combinations() if self._comb else {},
        }
        comb_str = self._comb.translate_to_str() if self._comb else None

        self._id["fq_name"] = Test.compute_fq_name(
            self._id["label"],
            self._id["subtree"],
            self._id["te_name"],
            suffix=kwargs.get("user_suffix", None),
            combination=comb_str,
        )

        # only positive ids
        self._id["jid"] = self.get_jid_from_name(self.name)

        self._execmd = kwargs.get("command", "")

        self._data = {
            "metrics": kwargs.get("metrics", {}),
            "tags": kwargs.get("tags", []),
            "artifacts": kwargs.get("artifacts", {}),
        }

        # validation parsing start:
        validation = kwargs.get("validation", {})
        self._expect_rc = validation.get("expect_exit", 0)
        self._time_validation = None
        if "time" in validation:
            self._time_validation = {
                "mean": validation["time"].get("mean", -1),
                "tolerance": validation["time"].get("tolerance", 0),
                "coef": validation["time"].get("coef", 1.5),
            }
        self._soft_timeout = validation.get("time", {}).get("soft_timeout", None)
        self._hard_timeout = validation.get("time", {}).get("hard_timeout", None)
        self._matchers = validation.get("match", None)
        self._analysis = validation.get("analysis", None)
        self._script = validation.get("script", {}).get("path", None)
        # validation pasring end

        self._has_hard_timeout = False

        self._mod_deps = kwargs.get("mod_deps", [])
        self._depnames = kwargs.get("job_deps", [])
        self._deps = []
        self._dependee = []
        self._invocation_cmd = self._execmd
        self._sched_cnt = 0
        self._output_info = {"file": None, "offset": -1, "length": 0}
        # alloc tracking number, used by job manager to track job allocation
        self.alloc_tracking = 0

    @property
    def jid(self) -> str:
        """Getter for unique Job ID within a run.

        This attribute is generally set by the manager once job is uploaded
        to the dataset.
        :return: the job id
        :rtype: an positive integer of -1 if not set
        """
        return self._id["jid"]

    @property
    def basename(self) -> str:
        return Test.compute_fq_name(self._id["label"], self._id["subtree"], self._id["te_name"])

    @property
    def tags(self):
        """Getter for the full list of tags.

        :return: the list of of tags
        :rtype: list
        """
        return self._data["tags"]

    @property
    def label(self):
        """Getter to the test label.

        :return: the label
        :rtype: str
        """
        return self._id["label"]

    @property
    def name(self):
        """Getter for fully-qualified job name.

        :return: test name.
        :rtype: str
        """
        return self._id["fq_name"]

    @property
    def subtree(self):
        """Getter to the test subtree.

        :return: test subtree.
        :rtype: str.
        """
        return self._id["subtree"]

    @property
    def te_name(self):
        """Getter to the test TE name.

        :return: test TE name.
        :rtype: str.
        """

        return self._id["te_name"]

    @property
    def combination(self):
        """Getter to the test combination dict.

        :return: test comb dict.
        :rtype: dict
        """

        return self._comb

    @property
    def command(self):
        """Getter for the full command.

        This is a real command, executed in a shell, coming from user's
        specificaition. It should not be confused with `invocation_command`.

        :return: unescaped command line
        :rtype: str
        """
        return self._execmd

    @property
    def invocation_command(self):
        """Getter for the list_of_test.sh invocation leading to run the job.

        This command is under the form: `sh /path/list_of_tests.sh <test-name>`

        :return: wrapper command line
        :rtype: str
        """
        return self._invocation_cmd

    @property
    def job_deps(self):
        """ "Getter to the dependency list for this job.

        The dependency struct is an array, where for each name (=key), the
        associated Job is stored (value)
        :return: the list of object-converted deps
        :rtype: list
        """
        return self._deps

    @property
    def job_depnames(self):
        """Getter to the list of deps, as an array of names.

        This array is emptied when all deps are converted to objects.

        :return: the array of dep names
        :rtype: list
        """
        return self._depnames

    @property
    def mod_deps(self):
        """Getter to the list of pack-manager rules defined for this job.

        There is no need for a ``_depnames`` version as these deps are provided
        as PManager objects directly.

        :return: the list of package-manager based deps.
        :rtype: list
        """
        return self._mod_deps

    @classmethod
    def get_jid_from_name(self, name):
        if not isinstance(name, bytes):
            name = str(name).encode("utf-8")

        return hashlib.md5(name).hexdigest()

    def get_dep_graph(self):
        res = {}
        for d in self._deps:
            res[d.name] = d.get_dep_graph()
        return res

    def resolve_a_dep(self, name, obj):
        """Resolve the dep object for a given dep name.

        :param name: the dep name to resolve, should be a valid dep.
        :type name: str
        :param obj: the dep object, should be a Test()
        :type obj: :class:`Test`
        """
        if name not in self._depnames:
            return

        if obj not in self._deps:
            self._deps.append(obj)

    def add_dependee(self, test):
        self._dependee.append(test)

    def remove_dependee(self, test):
        self._dependee.remove(test)

    def transpose_deps(self):
        for test in self._deps:
            test.add_dependee(self)

    def remove_test_from_deps(self):
        for test in self._deps:
            test.remove_dependee(self)

    def filter_run(self) -> bool:
        if len(self._dependee) > 0:
            return False

        filter_test: bool = True
        valcfg = GlobalConfig.root["validation"]
        if len(valcfg["run_filter"]["allow"]) > 0:
            for t in self.tags:
                if t in valcfg["run_filter"]["allow"]:
                    filter_test = False
            return filter_test

        filter_test = False
        for t in self.tags:
            if t in valcfg["run_filter"]["deny"]:
                filter_test = True
        return filter_test

    def has_completed_deps(self):
        """Check if the test can be scheduled.

        It ensures it hasn't been executed yet (or currently running) and all
        its deps are resolved and successfully run.

        :return: True if the job can be scheduled
        :rtype: bool
        """
        return len([d for d in self._deps if not d.been_executed()]) == 0

    def has_failed_dep(self):
        """Check if at least one dep is blocking this job from ever be
        scheduled.

        :return: True if at least one dep is shown a Failure state.
        :rtype: bool
        """
        for d in self._deps:
            if d.state in Test.BAD_STATES:
                return True
        return False

    def first_incomplete_dep(self):
        """Retrieve the first ready-for-schedule dep.

        This is mainly used to ease the scheduling process by following the job
        dependency graph.

        :return: a Test object if possible, None otherwise
        :rtype: :class:`Test` or NoneType
        """
        for d in self._deps:
            if d.state == Test.State.WAITING:
                return d
        return None

    @property
    def soft_timeout(self) -> int | None:
        """Getter for Test timeout in seconds.

        It cumulates timeout + tolerance, this value being passed to the
        subprocess.timeout.

        :return: an integer if a timeout is defined, None otherwise
        :rtype: int or NoneType
        """

        # timeout is (in order):
        # 1. explicitly defined
        # 2. OR extrapolated from defined result.mean
        # 3. set by default (GlobalConfig.root.validation.job_timeout)
        if self._soft_timeout:
            return self._soft_timeout
        if self._time_validation and self._time_validation["mean"] > 0:
            return (
                self._time_validation["mean"] + self._time_validation["tolerance"]
            ) * self._time_validation["coef"]
        return GlobalConfig.root["validation"]["soft_timeout"]

    @property
    def hard_timeout(self) -> int | None:
        """Getter for Test hard timeout in seconds.
        :return: an integer if timeout is defined, None otherwise.
        :rtype: int or NoneType
        """
        if self._hard_timeout:
            return self._hard_timeout
        return GlobalConfig.root["validation"]["hard_timeout"]

    def get_nb_nodes(self):
        """Return the orch-dimension value for this test.

        The dimension can be defined by the user and let the orchestrator knows
        what resource are, and how to 'count' them'. This accessor allow the
        orchestrator to extract the information, based on the key name.

        :return: The number of resource this Test is requesting.
        :rtype: int
        """
        if self._resources and len(self._resources) > 0:
            return self._resources[0]
        return 1

    @property
    def needed_resources(self) -> list[int]:
        """Return the resources used by the jobs

        :return: The number of nodes / cpus used by the jobs.
        :rtype: int
        """
        return self._resources

    def save_final_result(self, rc=0, time=None, out=b"", state=None):
        """Build the final Test result node.

        :param rc: return code, defaults to 0
        :type rc: int, optional
        :param time: elapsed time, defaults to 0.0
        :type time: float, optional
        :param out: standard out/err, defaults to b''
        :type out: bytes, optional
        :param state: Job final status (if override needed), defaults to FAILED
        :type state: :class:`Test.State`, optional
        """
        if state is None:
            state = Test.State.SUCCESS if self._expect_rc == rc else Test.State.FAILURE

        self.save_raw_run(rc=rc, out=out, time=time)
        self.save_status(state)
        self.save_artifacts()

    def save_artifacts(self):
        for elt_k, elt_v in self._data["artifacts"].items():
            if os.path.isfile(elt_v):
                with open(elt_v, "rb") as fh:
                    self._data["artifacts"][elt_k] = fh.read()

    def save_raw_run(self, out=None, rc=None, time=None, hard_timeout=False):
        """TODO:"""
        if rc is not None:
            self._rc = rc
        if out is not None:
            self._output = base64.b64encode(out)
            self._output_info["raw"] = self._output
        if time is not None:
            self._exectime = time
        self._has_hard_timeout = hard_timeout

    def extract_metrics(self):
        """TODO:"""
        raw_output = self.output
        for name in self._data["metrics"].keys():
            node = self._data["metrics"][name]

            try:
                ens = set if node["attributes"]["unique"] else list
            except KeyError:
                ens = list

            self._data["metrics"][name]["values"] = list(ens(re.findall(node["key"], raw_output)))

    def evaluate(self):
        """TODO:"""
        if self._has_hard_timeout:
            self._state = Test.State.HARD_TIMEOUT
            return

        state = Test.State.SUCCESS

        # validation by return code
        if self._expect_rc != self._rc:
            state = Test.State.FAILURE

        raw_output = self.output

        # validation through a matching regex
        if state == Test.State.SUCCESS and self._matchers is not None:
            for _, v in self._matchers.items():
                expected = v.get("expect", True) is True
                found = re.search(v["expr"], raw_output)
                io.console.debug(
                    f"Looking for expr: {v['expr']}, foud: {found}, expected: {expected}"
                )
                if (found and not expected) or (not found and expected):
                    state = Test.State.FAILURE
                    break

        # validation throw a plugin
        if state == Test.State.SUCCESS and self._analysis is not None:
            res = GlobalConfig.root.get_internal("pColl").invoke_plugins(
                Plugin.Step.TEST_RESULT_EVAL, analysis=self._analysis, job=self
            )
            if res is not None:
                state, self._soft_timeout = res

        # validation throw a custom script
        if state == Test.State.SUCCESS and self._script is not None:
            p = Program(self._script)
            p.run()
            if self._expect_rc != p.rc:
                state = Test.State.FAILURE

        # if the test succeed, check for soft timeout
        if (
            state == Test.State.SUCCESS
            and self._soft_timeout is not None
            and self.time > self._soft_timeout
        ):
            state = Test.State.SOFT_TIMEOUT

        self._state = state

    def save_status(self, state):
        """Set current Test state.

        :param state: give a special state to the test, defaults to FAILURE
        :param state: :class:`Test.State`, optional
        """
        self._state = state if isinstance(state, Test.State) else Test.State.FAILURE

    def should_print(self) -> bool:
        if not self._output:
            return False
        valcfg = GlobalConfig.root["validation"]

        # tags filtering override print policy
        if len(valcfg["print_filter"]["allow"]) > 0:
            for t in self.tags:
                if t in valcfg["print_filter"]["allow"]:
                    return True
        for t in self.tags:
            if t in valcfg["print_filter"]["deny"]:
                return False

        # print policy
        if valcfg["print_policy"] == "all":
            return True
        if valcfg["print_policy"] == "none":
            return False
        if valcfg["print_policy"] == "errors" and self.state in Test.BAD_STATES:
            return True
        return False

    def get_state_fancy(self):
        """Get the label, color & icon representing the status of the test."""
        label = str(self._state)
        color = "yellow"
        icon = ""

        if self._state == Test.State.SUCCESS:
            color = "green"
            icon = "succ"
        elif self._state in [Test.State.FAILURE, Test.State.HARD_TIMEOUT]:
            color = "red"
            icon = "fail"
        elif self._state in [Test.State.ERR_DEP, Test.State.ERR_OTHER, Test.State.SOFT_TIMEOUT]:
            color = "yellow"
            icon = "fail"
        return (label, color, io.console.utf(icon))

    def get_testinfo_fancy(self):
        label, color, icon = self.get_state_fancy()

        if self._state == Test.State.HARD_TIMEOUT:
            timeout = self.hard_timeout
        elif self._state == Test.State.SOFT_TIMEOUT:
            timeout = self.soft_timeout
        else:
            timeout = 0
        assert isinstance(timeout, int)
        timeout_str = f" ({timeout:5.2f}s)" if timeout > 0 else ""

        sep = io.console.utf("sep_v")
        return f"[{color} bold]   {icon} {self._exectime:8.2f}s{sep}{label:7}{timeout_str}{sep}{self.name}"

    def display(self):
        """Print the Test into stdout (through the manager)."""

        raw_output = None
        if self.should_print():
            raw_output = self.output

        io.console.print_job(
            self.get_testinfo_fancy(),
            self._state,
            self.label,
            "/{}".format(self.subtree) if self.subtree else "",
            raw_output,
        )

    def been_executed(self):
        """Check if job has been executed (not waiting or in progress).

        :return: False if job is waiting for scheduling or in progress.
        :rtype: bool
        """
        return self._state not in [Test.State.WAITING, Test.State.IN_PROGRESS, Test.State.EXECUTED]

    def pick(self):
        """Flag the job as picked up for scheduling."""
        self._state = Test.State.IN_PROGRESS

    def is_never_picked(self):
        self._sched_cnt += 1
        return self._sched_cnt >= self.SCHED_MAX_ATTEMPTS

    def pick_count(self):
        return self._sched_cnt

    @property
    def state(self):
        """Getter for current job state.

        :return: the job current status.
        :rtype: :class:`Test.State`
        """
        return self._state

    @property
    def encoded_output(self) -> bytes:
        return self._output

    @encoded_output.setter
    def encoded_output(self, v) -> None:
        self._output = v
        self._output_info["raw"] = v

    def get_raw_output(self, encoding="utf-8") -> bytes:
        base = base64.b64decode(self._output)

        return base if not encoding else base.decode(encoding)

    @property
    def output(self) -> str:
        return self.get_raw_output(encoding="utf-8")

    @property
    def output_info(self) -> dict:
        return self._output_info

    @property
    def time(self):
        """TODO:"""
        return self._exectime

    @property
    def retcode(self):
        return self._rc

    def to_json(self, strstate=False):
        """Serialize the whole Test as a JSON object.

        :return: a JSON object mapping the test
        :rtype: str
        """
        res = {
            "id": self._id,
            "exec": self._execmd,
            "result": {
                "rc": self._rc,
                "state": str(self._state) if strstate else self._state,
                "time": self._exectime,
                "output": self._output_info,
            },
            "data": self._data,
        }

        return res

    def to_minimal_json(self):
        return {
            "jid": self.jid,
            "invocation_cmd": self._invocation_cmd,
        }

    def from_minimal_json(self, jsonstr: str):
        if isinstance(jsonstr, str):
            jsonstr = json.loads(jsonstr)
        self._invocation_cmd = jsonstr.get("invocation_cmd", "exit 1")
        self._id["jid"] = jsonstr.get("jid", "-1")

    def from_json(self, test_json: str, filepath: str) -> None:
        """Replace the whole Test structure based on input JSON.

        :param json: the json used to set this Test
        :type json: test-result-valid JSON-formatted str
        """

        if isinstance(test_json, str):
            test_json = json.loads(test_json)

        assert isinstance(test_json, dict)
        self.res_scheme.validate(test_json, filepath)

        self._id = test_json.get("id", -1)
        self._comb = Combination({}, self._id.get("comb", {}), None)
        self._execmd = test_json.get("exec", "")
        self._data = test_json.get("data", "")

        res = test_json.get("result", {})
        self._rc = res.get("rc", -1)
        self._state = Test.State(res.get("state", Test.State.ERR_OTHER))
        self._exectime = res.get("time", 0)
        self._output_info = res.get("output", {})
        self._output = self._output_info.get("raw", b"")
        if self._output is str:
            # should only be managed as bytes (as produced by b64 encoding)
            self._output = self._output.encode("utf-8")

    def generate_script(self, srcfile):
        """Serialize test logic to its Shell representation.

        This script provides the shell sequence to put in a shell script
        switch-case, in order to reach that test from script arguments.

        :param srcfile: script filepath, to store the actual wrapped command.
        :type srcfile: str
        :return: the shell-compliant instruction set to build the test
        :rtype: str
        """
        pm_code = ""
        cd_code = ""
        env_code = ""
        cmd_code = ""

        self._invocation_cmd = "bash {} {}".format(srcfile, self._id["fq_name"])

        # if changing directory is required by the test
        if self._cwd is not None:
            cd_code += "cd '{}'".format(shlex.quote(self._cwd))

        # manage package-manager deps
        for elt in self._mod_deps:
            pm_code += "\n".join([elt.get(load=True, install=True)])

        # manage environment variables defined in TE
        if self._testenv is not None:
            envs = []
            for e in self._testenv:
                k, v = e.split("=", 1)
                envs.append("{k}={v}; export {k}".format(k=shlex.quote(k), v=shlex.quote(v)))
            env_code = "\n".join(envs)

        cmd_code = self._execmd

        return """
        "{name}")
            {cd_code}
            pcvs_load={pm_code}
            pcvs_env={env_code}
            pcvs_cmd={cmd_code}
            ;;""".format(
            cmd_code="{}".format(shlex.quote(cmd_code)),
            env_code="{}".format(shlex.quote(env_code)),
            pm_code="{}".format(shlex.quote(pm_code)),
            cd_code=cd_code,
            name=self._id["fq_name"],
        )

    @classmethod
    def compute_fq_name(self, label, subtree, name, suffix=None, combination=None):
        """Generate the fully-qualified (dq) name for a test, based on :
        - the label & subtree (original FS tree)
        - the name (the TE name it is originated)
        - a potential extra suffix
        - the combination PCVS computed for this iteration."""
        assert label
        assert subtree
        assert name
        path = os.path.normpath(os.path.join(label, subtree, name))
        return "_".join(filter(None, [path, suffix, combination]))

    def __repr__(self):
        return repr(self.__dict__)

    def __rich_repr__(self):
        return self.__dict__.items()
