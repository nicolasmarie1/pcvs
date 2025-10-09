import copy
import os
import re
import shutil
import tempfile

import pcvs
from pcvs import io
from pcvs import testing
from pcvs.helpers import pm
from pcvs.helpers.criterion import Criterion
from pcvs.helpers.criterion import Series
from pcvs.helpers.exceptions import ProfileException
from pcvs.helpers.exceptions import TestException
from pcvs.helpers.system import GlobalConfig
from pcvs.testing.test import Test

# now return the first valid language, according to settings
# order matters: if sources contains multiple languages, the first
# appearing in this list will be considered as the main language


def detect_compiler(array_of_files) -> str:
    """
    Determine compilers to use for a target file (or list of files).

    :param array_of_files: list of files to identify
    :return: the chosen compilers
    """
    detect = []
    for f in array_of_files:
        for comp_name, compiler in GlobalConfig.root["compiler"]["compilers"].items():
            if compiler["extension"] and re.search(compiler["extension"], f):
                detect.append(comp_name)
                break
        else:
            detect.append(None)
    return detect


def extract_compilers_envs():
    """Extract compilers environment."""
    envs = []
    for _, compiler in GlobalConfig.root["compiler"]["compilers"].items():
        envs += compiler.get("envs", [])
    return envs


def extract_compiler_config(lang, variants):
    """
    Build resource to compile based on language and variants involved.

    :param lang: target compiler name
    :type lang: str
    :param variants: list of enabled variants
    :type variants: list
    :return: the program, its args and env modifiers (in that order)
    :rtype: tuple
    """
    if not lang or lang not in GlobalConfig.root["compiler"]["compilers"]:
        raise ProfileException.IncompleteError(
            reason="Unknown compiler, not defined into Profile",
            dbg_info={"lang": lang, "list": GlobalConfig.root["compiler"]["compilers"].keys()},
        )

    config = GlobalConfig.root["compiler"]["compilers"][lang]
    for v in variants:
        if v in config["variants"]:
            for k, v in config["variants"][v].items():
                if k == "program":
                    config[k] = v
                else:
                    config.setdefault(k, [])
                    config[k] += v
        else:
            # TODO: throw error here
            return (None, [], [], False)

    return (
        config["program"],
        config.get("args", []),
        config.get("envs", []),
        config.get("valid", False),
    )


def build_job_deps(deps_node, pkg_label, pkg_prefix):
    """
    Build the dependency list from a given dependency YAML node.

    A ``depends_on`` is used by test to establish their relationship. It looks
    like:

    :example:
        depends_on:
            ["list_of_test_name"]

    :param deps_node: the TE/job YAML node.
    :type deps_node: dict
    :param pkg_label: the label where this TE is from (to compute depnames)
    :type pkg_label: str
    :param pkg_prefix: the subtree where this TE is from (to compute depnames)
    :type pkg_prefix: str or NoneType

    :return: a list of dependencies, either as depnames or PManager objects
    :rtype: list
    """
    deps = []
    for d in deps_node.get("depends_on", []):
        deps.append(d if "/" in d else Test.compute_fq_name(pkg_label, pkg_prefix, d))
    return deps


def build_pm_deps(deps_node):
    """Build the dependency list from a given YAML node.

    This only initialize package-manager oriented deps. For job deps, see
    ``build_job_deps``

    :param deps_node: contains package_manager YAML information
    :type deps_node: str
    :return: a list of PM objects, one for each entry
    :rtype: List[:class:`PManager`]
    """
    return pm.identify(deps_node.get("package_manager", {}))


class TEDescriptor:
    """A Test Descriptor (named TD, TE or TED), maps a test program
    representation, as defined by a root node in a single test files.

    A TE Descriptor is not a test but a definition of a program (how to use it,
    to compile it...), leading to a collection once combined with a profile
    (providing on which MPI processes to run it, for instance).

    :ivar _te_name: YAML root node name, part of its unique id
    :type _te_name: str
    :ivar _te_label: which user directory this TE is coming from
    :type _te_label: str
    :ivar _te_subtree: subprefix, relative to label, where this TE is located
    :type _te_subtree: str or NoneType
    :ivar _full_name: fully-qualified te-name
    :type _full_name: str
    :ivar _srcdir: absolute path pointing to the YAML testfile dirname
    :type _srcdir: str
    :ivar _buildir: absolute path pointing to build equivalent of _srcdir
    :type _buildir: str
    :ivar _skipped: flag if this TE should be unfolded to tests or not
    :type _skipped: bool
    :ivar _effective_cnt: number of tests created by this single TE
    :type _effective_cnt: int
    :ivar _program_criterion: extra criterion defined by the TE
    :type _program_criterion: :class:`Criterion`
    :ivar others: used yaml node references.
    """

    @classmethod
    def init_system_wide(cls, base_criterion_name):
        """
        Initialize system-wide information (to shorten accesses).

        :param base_criterion_name: iterator name used as scheduling resource.
        :type base_criterion_name: str
        """
        cls._sys_crit = GlobalConfig.root.get_internal("crit_obj")
        cls._base_it = base_criterion_name

    def __init__(self, name, node, label, subprefix):
        """
        Constructor method.

        :param name: the TE name
        :type name: str
        :param node: the TE YAML content.
        :type node: str
        :param label: the user dir label.
        :type label: str
        :param subprefix: relative path between user dir & current TE testfile
        :type subprefix: str or NoneType

        :raises TDFormatError: Unproper YAML TE format (sanity check)
        """
        if not isinstance(node, dict):
            raise TestException.TestExpressionError(node)

        self._te_name = name
        self._skipped = name.startswith(".")
        self._te_label = label
        self._te_subtree = subprefix

        _, self._srcdir, _, self._buildir = testing.generate_local_variables(label, subprefix)
        # before doing anything w/ node:
        # arregate the 'group' definitions with the TE
        # to get all the fields in their final form
        if "group" in node and node["group"] in GlobalConfig.root["group"].keys():
            tmp = GlobalConfig.root["group"][node["group"]]
            tmp.update(node)
            node = tmp
        # load from descriptions
        self._build = node.get("build", {})
        self._run = node.get("run", {})
        self._validation = node.get("validate", {})
        self._build_validation = self._build.get("validate", {})
        self._artifacts = node.get("artifact", {})
        self._metrics = node.get("metrics", {})
        self._attributes = node.get("attributes", {})
        self._template = node.get("group", {})
        self._debug = self._te_name + ":\n"
        self._effective_cnt = 0
        self._tags = node.get("tag", [])

        path_prefix = self._buildir
        if self.get_attr("path_resolution", True) is False:
            path_prefix = ""

        for elt_k, elt_v in self._artifacts.items():
            if not os.path.isabs(elt_v):
                self._artifacts[elt_k] = os.path.join(path_prefix, elt_v)

        # allow tags to be given as array OR a single string
        if not isinstance(self._tags, list):
            self._tags = [self._tags]

        # if TE used program-level criterions
        if "program" in self._run.get("iterate", {}):
            self._program_criterion = {
                k: Criterion(k, v, local=True) for k, v in self._run["iterate"]["program"].items()
            }
        else:
            self._program_criterion = {}

        # compute local criterions relatively to system-wide's
        self._configure_criterions()
        # apply retro-compatibility w/ old syntax
        self._compatibility_support(node.get("_compat", None))

    def get_binary_name(self):
        """
        Get the binary name for the file at the output of the compiler.

        If a binary name is already defined by the test, use it.
        If a program name is given, use it.
        If none are defined, use the test name.
        """
        if "binary" in self._build.get("sources", {}):
            return self._build["sources"]["binary"]
        if "program" in self._run:
            return self._run["program"]
        return self._te_name

    def get_attr(self, name, dflt=None):
        if name in self._attributes:
            return self._attributes[name]
        else:
            return dflt

    def _compatibility_support(self, compat):
        """Convert tricky keywords from old syntax too complex to be handled
        by the automatic converter.

        :param compat: dict of complex keyword extracted from old syntax.
        :param compat: dict or NoneType
        """
        if compat is None:
            return
        for k in compat:
            # the old 'chdir' may be used by run & build
            # but should not be set for one if the whole
            # parent node does not exist
            if "chdir" in k:
                if self._build and "cwd" not in self._build:
                    self._build["cwd"] = compat[k]
                if self._run and "cwd" not in self._run:
                    self._run["cwd"] = compat[k]

            # the old 'type' keyword disappeared. Still, the 'complete'
            # keyword must be handled to create both nodes 'build' & 'run'
            if "type" in k:
                if compat[k] in ["build", "complete"]:
                    self._build["dummy"] = True
                if compat[k] in ["run", "complete"]:
                    self._run["dummy"] = True

            # same as for chdir, 'bin' may be used by both build & run
            # but should set either not existing already
            elif "bin" in k:
                if self._build and "binary" not in self._build:
                    self._build["binary"] = compat[k]
                if self._run and "program" not in self._run:
                    self._run["program"] = compat[k]

        if "cflags" in self._build and "sources" in self._build:
            self._build["sources"]["cflags"] = self._build["cflags"]
        if "ldflags" in self._build and "sources" in self._build:
            self._build["sources"]["ldflags"] = self._build["ldflags"]
        if "params" in self._build.get("autotools", {}):
            self._build["autotools"]["args"] = self._build["autotools"]["params"]
        if "vars" in self._build.get("cmake", {}):
            self._build["cmake"]["args"] = self._build["cmake"]["vars"]

    def _configure_criterions(self):
        """Prepare the list of components this TE will be built against.

        It consists in intersecting system-wide criterions and their
        definitions with this overridden criterion by this TE. The result is then
        what tests will be built on. If there is no intersection between
        system-wide and this TE declaration, the whole TE is skipped.
        """
        if self._run is None:
            # for now, criterion only applies to run tests
            return
        # if this TE does not override anything: trivial
        if "iterate" not in self._run:
            self._criterion = self._sys_crit
        else:
            te_keys = self._run["iterate"].keys()
            tmp = {}
            # browse declared criterions (system-wide)
            for k_sys, v_sys in self._sys_crit.items():
                # if key is overridden by the test
                if k_sys in te_keys:
                    cur_criterion = copy.deepcopy(v_sys)
                    cur_criterion.override(self._run["iterate"][k_sys])

                    if cur_criterion.is_discarded():
                        continue
                    # merge manually some definitions made by
                    # runtime, as some may be required to expand values:

                    cur_criterion.expand_values(v_sys)
                    cur_criterion.intersect(v_sys)
                    if cur_criterion.is_empty():
                        self._skipped = True
                    else:
                        tmp[k_sys] = cur_criterion
                else:  # key is not overridden
                    tmp[k_sys] = v_sys

            self._criterion = tmp
            # now build program iterators
            for _, elt in self._program_criterion.items():
                elt.expand_values()

    def __build_from_sources(self):
        """How to create build tests from a collection of source files.

        :return: the command to be used.
        :rtype: str
        """
        compilers = detect_compiler(self._build["files"])
        if len(compilers) < 1 or compilers[0] is None:
            raise TestException.TestExpressionError(
                self._build["files"], f"Unable to dect compilers for files: {self._build['files']}"
            )

        compiler = compilers[0]

        compiler_config = extract_compiler_config(compiler, self._build.get("variants", {}))
        program, args, envs, valid = compiler_config
        if not valid:
            io.console.warn(f"Compiler program '{program}' not found for test '{self.name}'")

        binary = self.get_binary_name()

        # used to run the test later
        self._build.setdefault("sources", {})["binary"] = binary
        output_path = os.path.join(self._buildir, binary)

        command = "{cc} {cflags} {files} {ldflags} {args} {out}".format(
            cc=program,
            cflags=self._build["sources"].get("cflags", ""),
            files=" ".join(self._build["files"]),
            ldflags=self._build["sources"].get("ldflags", ""),
            args=" ".join(args),
            out=f"-o {output_path}",
        )
        return (command, envs, 1)

    def __build_from_makefile(self):
        """How to create build tests from a Makefile.

        :return: the command to be used.
        :rtype: str
        """
        command = ["make"]
        basepath = self._srcdir

        # change makefile path if overridden by 'files'
        if "files" in self._build:
            basepath = os.path.dirname(self._build["files"][0])
            command.append("-f {}".format(" ".join(self._build["files"])))

        envs = extract_compilers_envs()
        jobs = self._build.get("make", {}).get("jobs", 1)
        # build the 'make' command
        command.append(f"-j {jobs}")
        command.append(
            "-C {path} {target}".format(
                path=basepath, target=self._build.get("make", {}).get("target", "")
            )
        )
        command += self._build.get("make", {}).get("args", [])
        envs += self._build.get("make", {}).get("envs", [])

        return (" ".join(command), envs, jobs)

    def __build_from_cmake(self):
        """How to create build tests from a CMake project.

        :return: the command to be used.
        :rtype: str
        """
        command = ["cmake"]
        if "files" in self._build:
            command.append(self._build["files"][0])
        else:
            command.append(self._srcdir)

        envs = extract_compilers_envs()
        command.append(
            r"-G 'Unix Makefiles' " r"-DCMAKE_BINARY_DIR='{build}' ".format(build=self._buildir)
        )

        command += self._build["cmake"].get("args", [])
        envs += self._build["cmake"].get("envs", [])

        self._build["files"] = [os.path.join(self._buildir, "Makefile")]
        tmp = self.__build_from_makefile()
        next_command = tmp[0]
        envs += tmp[1]
        return (" && ".join([" ".join(command), next_command]), envs, tmp[2])

    def __build_from_autotools(self):
        """How to create build tests from a Autotools-based project.

        :return: the command to be used.
        :rtype: str
        """
        command = []
        configure_path = ""
        autogen_path = ""

        if self._build.get("files", False):
            configure_path = self._build["files"][0]
        else:
            configure_path = os.path.join(self._srcdir, "configure")

        if self._build["autotools"].get("autogen", False) is True:
            autogen_path = os.path.join(os.path.dirname(configure_path), "autogen.sh")
            command.append("{} && ".format(autogen_path))

        envs = extract_compilers_envs()

        command.append(r"{configure} ".format(configure=configure_path))

        command += self._build["autotools"].get("args", [])
        envs += self._build["autotools"].get("envs", [])

        self._build["files"] = [os.path.join(self._buildir, "Makefile")]
        tmp = self.__build_from_makefile()
        next_command = tmp[0]
        envs += tmp[1]
        return (" && ".join([" ".join(command), next_command]), envs, tmp[2])

    def __build_from_user_script(self):
        command = []
        env = []

        command = self._build["custom"].get("program", "echo")
        # args not relevant as cflags/ldflags can be used instead
        env = self._build["custom"].get("envs", [])

        if not os.path.isabs(command):
            command = os.path.join(self._buildir, command)

        full_cmd = ". {} && {}".format(
            os.path.join(GlobalConfig.root["validation"]["output"], pcvs.NAME_BUILD_CONF_SH),
            command,
        )
        return (full_cmd, env, 1)

    def __build_exec_process(self):
        """Drive compilation command generation based on TE format.

        :return: the command to be used.
        :rtype: str
        """
        if "autotools" in self._build:
            return self.__build_from_autotools()
        if "cmake" in self._build:
            return self.__build_from_cmake()
        if "make" in self._build:
            return self.__build_from_makefile()
        if "custom" in self._build:
            return self.__build_from_user_script()
        return self.__build_from_sources()

    def __construct_compil_tests(self):
        """Meta-function steering compilation tests."""
        job_deps = []

        # ensure consistency when 'files' node is used
        # can be a list or a single value
        if "files" in self._build:
            if not isinstance(self._build["files"], list):
                self._build["files"] = [self._build["files"]]

            for i in range(0, len(self._build["files"])):
                if not os.path.isabs(self._build["files"][i]):
                    self._build["files"][i] = os.path.join(self._srcdir, self._build["files"][i])

        # manage deps (tests, package_managers...)
        job_deps = build_job_deps(self._build, self._te_label, self._te_subtree)
        mod_deps = build_pm_deps(self._build)

        chdir = self._build.get("cwd")
        if chdir is not None and not os.path.isabs(chdir):
            chdir = os.path.abspath(os.path.join(self._buildir, chdir))

        tags = ["compilation"] + self._tags

        command, env, jobs = self.__build_exec_process()
        wrapper = GlobalConfig.root["runtime"].get("compiling", {}).get("wrapper", "")
        command = f"{wrapper} {command}"
        assert jobs is not None

        # count number of built tests
        self._effective_cnt += 1

        yield Test(
            te_name=self._te_name,
            user_suffix="cc" if self._run else None,
            label=self._te_label,
            subtree=self._te_subtree,
            command=command,
            environment=env,
            tags=tags,
            job_deps=job_deps,
            mod_deps=mod_deps,
            artifacts=self._artifacts,
            resources=[1, jobs],  # 1 node / jobs cores.
            wd=chdir,
            validation=self._build_validation,
        )

    def __construct_runtime_tests(self, series):
        """Generate tests to be run by the runtime command."""
        te_job_deps = build_job_deps(self._run, self._te_label, self._te_subtree)
        te_mod_deps = build_pm_deps(self._run)

        if self._build:
            fq_name = Test.compute_fq_name(self._te_label, self._te_subtree, self._te_name, "cc")
            if fq_name not in te_job_deps:
                te_job_deps.append(fq_name)

        # for each combination generated from the collection of criterions
        for comb in series.generate():
            chdir = None

            # start to build the proper command, three parts:
            # the environment variables to export
            # the runtime argument to propagate
            # the program parameters to forward
            env, args, params = comb.translate_to_command()
            program = self.get_binary_name()

            clone_outdir = self.get_attr("copy_output", False)
            if clone_outdir:
                buildir = tempfile.mkdtemp(prefix="{}.".format(self._te_name), dir=self._buildir)
            else:
                buildir = self._buildir

            # attempt to determine test working directory
            chdir = self._run["cwd"] if "cwd" in self._run else buildir

            if not os.path.isabs(chdir):
                chdir = os.path.abspath(os.path.join(buildir, chdir))

            # keep the original value if user disabled prefix resolution
            if self.get_attr("path_resolution", True) is True:
                program = os.path.abspath(os.path.join(self._buildir, program))

            command = "{program} {params}".format(program=program, params=" ".join(params))
            if self.get_attr("command_wrap", True) is True:
                command = "{runtime} {args} {runtime_args} {cmd}".format(
                    runtime=GlobalConfig.root["runtime"].get("program", ""),
                    runtime_args=GlobalConfig.root["runtime"].get("args", ""),
                    args=" ".join(args),
                    cmd=command,
                )
            self._effective_cnt += 1

            yield Test(
                te_name=self._te_name,
                label=self._te_label,
                subtree=self._te_subtree,
                command=command,
                job_deps=te_job_deps,
                mod_deps=te_mod_deps,
                tags=self._tags,
                metrics=self._metrics,
                environment=env,
                comb=comb,
                resources=comb.resources if comb.resources is not None else [1, 1],
                wd=chdir,
                validation=self._validation,
                artifacts=self._artifacts,
            )

    @io.capture_exception(Exception, doexit=True)
    def construct_tests(self):
        """Construct a collection of tests (build & run) from a given TE.

        This function will process a YAML node and, through a generator, will
        create each test coming from it.
        """
        # if this TE does not lead to a single test, skip now
        if self._skipped:
            return

        clone_indir = self.get_attr("copy_input", False)

        if clone_indir:
            isolation_path = tempfile.mkdtemp(prefix="{}.".format(self._te_name), dir=self._buildir)
            old_src_dir = self._srcdir
            self._srcdir = os.path.join(isolation_path, "src")
            shutil.copytree(old_src_dir, self._srcdir)
            self._buildir = os.path.join(isolation_path, "build")
            os.mkdir(self._buildir)

        if self._build:
            yield from self.__construct_compil_tests()
        if self._run:
            if self.get_attr("command_wrap", True) is False:
                series = Series({**self._program_criterion})
            else:
                series = Series({**self._criterion, **self._program_criterion})
            yield from self.__construct_runtime_tests(series)

    def get_debug(self):
        """Build information debug for the current TE.

        :return: the debug info
        :rtype: dict
        """
        # if the current TE did not lead to a single test, skip now
        if self._skipped:
            return {}

        debug_yaml = {}

        # count actual tests built
        if self._run:
            # for system-wide iterators, count max number of possibilities
            for k, v in self._criterion.items():
                debug_yaml[k] = list(v.values)

            # for program-level iterators, count number of possibilities
            debug_yaml["program"] = dict()
            for k, v in self._program_criterion.items():
                debug_yaml["program"][k] = list(v.values)

        return debug_yaml

    @property
    def name(self):
        """Getter to the current TE name.

        :return: te_name
        :rtype: str
        """
        return self._te_name

    def __repr__(self):
        """Internal TE representation, for auto-dumping.

        :return: the node representation.
        :rtype: str
        """
        return repr(self._build) + repr(self._run) + repr(self._validation)
