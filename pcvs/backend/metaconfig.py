import os

from ruamel.yaml import YAML
from ruamel.yaml import YAMLError

import pcvs
from pcvs import NAME_BUILDIR
from pcvs.backend.config import Config
from pcvs.backend.profile import Profile
from pcvs.helpers import git
from pcvs.helpers import pm
from pcvs.helpers.exceptions import CommonException
from pcvs.helpers.validation import ValidationScheme
from pcvs.io import Verbosity


class MetaConfig(Config):
    """
    Root configuration object.

    It is composed of Config(), categorizing each configuration blocks.
    This MetaConfig() contains the whole profile along with
    any validation and current run information.
    This configuration is used as a dict extension.

    The internal_config is used to contain runtime information that should/could not be serialize.
    """

    def __init__(self, d: dict = {}, internal_config: dict = {}):
        """
        Init the object.

        :param d: items of the configuration
        :type d: dict
        """
        super().__init__(d)
        self.__internal_config = internal_config

    def bootstrap_from_profile(self, pf: Profile) -> None:
        """Bootstrap MetaConfig from profile."""
        self.bootstrap_compiler(pf.compiler)
        self.bootstrap_criterion(pf.criterion)
        self.bootstrap_group(pf.group)
        self.bootstrap_machine(pf.machine)
        self.bootstrap_runtime(pf.runtime)

    def bootstrap_compiler(self, conf: Config) -> None:
        """
        Specific initialize for compiler config.

        :param conf: compiler config to initialize
        :type conf: Config
        """
        self.set_nosquash("compiler", conf)
        if "package_manager" in conf:
            self.set_internal("cc_pm", pm.identify(conf["package_manager"]))

    def bootstrap_criterion(self, conf: Config) -> None:
        """
        Specific initialize for criterion config.

        :param conf: criterion config to initialize
        :type conf: Config
        """
        self.set_nosquash("criterion", conf)

    def bootstrap_group(self, conf: Config) -> None:
        """
        Specific initialize for group config.

        :param node: group config to initialize
        :type node: Config
        """
        self.set_nosquash("group", conf)

    def bootstrap_machine(self, conf: Config) -> None:
        """
        Specific initialize for machine config block.

        :param conf: machine config to initialize
        :type conf: Config
        """
        self.set_nosquash("machine", conf)

        conf.set_nosquash("name", "default")
        conf.set_nosquash("nodes", 1)
        conf.set_nosquash("cores_per_node", 1)
        conf.set_nosquash("concurrent_run", 1)

        if "default_partition" not in conf or "partitions" not in conf:
            return

        # override default values by selected partition
        for elt in conf.get("partitions", []):
            if elt["name"] == conf["default_partition"]:
                conf.update(elt)
                break

        # redirect to direct programs if no wrapper is defined
        for kind in ["allocate", "remote", "batch"]:
            if not conf["job_manager"][kind]["wrapper"] and conf["job_manager"][kind]["program"]:
                conf["job_manager"][kind]["wrapper"] = conf["job_manager"][kind]["program"]

    def bootstrap_runtime(self, conf: Config) -> None:
        """Specific initialize for runtime config.

        :param node: runtime config to initialize
        :type node: Config
        """
        self.set_nosquash("runtime", conf)
        if "package_manager" in conf:
            self.set_internal("rt_pm", pm.identify(conf["package_manager"]))

    def bootstrap_validation_from_file(self, filepath: str) -> None:
        """
        Specific initialize for validation config block.

        This function loads a file containing the validation dict.
        :param filepath: path to file to be validated
        :type filepath: str
        :raises IOError: file is not found or badly formatted
        """
        node = {}
        if filepath is None:
            filepath = pcvs.PATH_VALCFG

        if os.path.isfile(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as fh:
                    node = YAML(typ="safe").load(fh)
            except (IOError, YAMLError) as e:
                raise CommonException.IOError(f"Error(s) found while loading {filepath}") from e

        conf: Config = Config(node)
        ValidationScheme("validation").validate(conf, filepath)

        # some post-actions
        for field in ["output", "reused_build"]:
            if field in conf:
                conf[field] = os.path.abspath(conf[field])

        if "dirs" in conf:
            conf["dirs"] = {k: os.path.abspath(v) for k, v in conf["dirs"].items()}

        self.bootstrap_validation(conf)

    def bootstrap_validation(self, conf: Config) -> None:
        """
        Specific initialize for validation config.

        :param node: validation block to initialize
        :type node: dict
        """
        self.set_nosquash("validation", conf)

        # Initialize default values when not set by user or default files
        conf.set_nosquash("verbose", str(Verbosity.COMPACT))
        conf.set_nosquash("print_policy", "none")
        conf.set_nosquash("color", True)
        conf.set_nosquash("default_profile", "default")
        conf.set_nosquash("output", os.path.join(os.getcwd(), NAME_BUILDIR))
        conf.set_nosquash("background", False)
        conf.set_nosquash("override", False)
        conf.set_nosquash("dirs", None)
        conf.set_nosquash("spack_recipe", None)
        conf.set_nosquash("simulated", False)
        conf.set_nosquash("anonymize", False)
        conf.set_nosquash("onlygen", False)
        conf.set_nosquash("timeout", None)
        conf.set_nosquash("target_bank", None)
        conf.set_nosquash("reused_build", None)
        conf.set_nosquash("webreport", None)
        conf.set_nosquash("only_success", False)
        conf.set_nosquash("enable_report", False)
        conf.set_nosquash("hard_timeout", 3600)
        conf.set_nosquash("soft_timeout", None)
        conf.set_nosquash("per_result_file_sz", 10 * 1024 * 1024)
        conf.set_nosquash("buildcache", os.path.join(conf["output"], "cache"))
        conf.set_nosquash("result", {"format": ["json"]})
        conf.set_nosquash(
            "author", {"name": git.get_current_username(), "email": git.get_current_usermail()}
        )

        if "format" not in conf["result"]:
            conf["result"]["format"] = ["json"]
        if "log" not in conf["result"]:
            conf["result"]["log"] = 1
        if "logsz" not in conf["result"]:
            conf["result"]["logsz"] = 1024

        return conf

    def set_internal(self, k, v):
        """
        Manipulate the internal MetaConfig() node to store unexportable data.

        :param k: name of value to add
        :type k: str
        :param v: value to add
        :type v: str
        """
        self.__internal_config[k] = v

    def get_internal(self, k):
        """
        Manipulate the internal MetaConfig() node to load unexportable data.

        :param k: value to get
        :type k: str
        """
        if k in self.__internal_config:
            return self.__internal_config[k]
        return None


class GlobalConfig:
    """
    A static class to store a Global version of Metaconfig.

    To avoid carrying a global instancied object over the whole code, a
    class-scoped attribute allows to browse the global configuration from
    anywhere through `GlobalConfig.root`"
    """

    root = MetaConfig()
