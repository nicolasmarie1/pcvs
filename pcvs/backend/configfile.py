import os
from io import StringIO

import click
from ruamel.yaml import YAML
from typeguard import typechecked

from pcvs import io
from pcvs.backend.config import Config
from pcvs.helpers.storage import ConfigDesc
from pcvs.helpers.storage import ConfigKind
from pcvs.helpers.storage import ConfigLocator
from pcvs.helpers.storage import ConfigScope
from pcvs.helpers.validation import ValidationScheme


@typechecked
class ConfigFile:
    # TODO: rewrite doc
    """
    Handle configuration file.

    From a user persperctive, a basic block is a dict, gathering in a Python
    object information relative to the configuration of a single component.
    In PCVS, there is 7 types of components:

    5 basic blocks:

    * Compiler (defining compiler commands)
    * Runtime (setting runtime & parametrization)
    * Machine (Defining resources used for execution)
    * Group (used a templates to globally describe tests)
    * Criterion (range of parameters used to run a test-suite)


    2 special:

    * Profile (a group of one of each the above configuration)
    * Plugin (a python plugin)

    This class helps to manage any of these config blocks above. The
    distinction between them is carried over by an instance attribute
    ``_kind``.

    :param str _kind: which component this object describes
    :param str _name: block name
    :param dict details: block content
    :param str _scope: block scope, may be None
    :param str _file: absolute path for the block on disk
    :param bool _exists: True if the block exist on disk
    """

    def __init__(self, config_desc: ConfigDesc):
        """Initialize a configuration file representation."""
        self._descriptor: ConfigDesc = config_desc
        self._raw: str = ""
        if self.exist:
            self._load_from_disk()
            self._check()

    # Private unguarded functions
    def _check(self) -> None:
        """Validate a config according to its scheme, look at super class."""

    def _load(self, raw: str) -> None:
        self._raw = raw

    def _flush(self) -> str:
        return self._raw

    def _load_from_disk(self) -> None:
        with open(self._descriptor.path, encoding="utf-8") as f:
            self._load(f.read())

    def _flush_to_disk(self) -> None:
        raw: str = self._flush()
        # create dir if it does not exist
        self._descriptor.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._descriptor.path, "w", encoding="utf-8") as f:
            f.write(raw)

    # Public safe functions

    # Property for Disk Loading & ObjectFilling choerency management.
    @property
    def exist(self) -> bool:
        """Return if the config file exist on disk."""
        return self._descriptor.exist

    @property
    def loaded(self) -> bool:
        """Return if the config is loaded in Object."""
        return self._raw != ""

    # Accessors
    @property
    def descriptor(self) -> ConfigDesc:
        """Return the description of the config file."""
        return self._descriptor

    @property
    def full_name(self) -> str:
        """Return full name."""
        return self._descriptor.full_name

    # Config IO from file
    def load_from_disk(self) -> None:
        """Load the configuration file to populate the current object."""
        assert self.exist
        self._load_from_disk()
        self._check()

    def flush_to_disk(self) -> None:
        """Write the configuration to disk."""
        assert self.loaded
        self._check()
        self._flush_to_disk()

    def delete(self) -> None:
        """Delete a configuration from disk."""
        assert self.exist
        io.console.info(
            f"Remove {self._descriptor.name} from '{self._descriptor.kind} ({self._descriptor.scope})'"
        )
        os.remove(self._descriptor.path)

    def edit(self) -> None:
        """Open the current configuration for edition.

        :raises Exception: Something occurred on the edited version.
        """
        assert self.exist
        self._load_from_disk()
        edited_stream = click.edit(
            self._raw, extension=ConfigKind.get_file_ext(self._descriptor.kind), require_save=True
        )
        if edited_stream is not None:
            self._load(edited_stream)
            self._check()
            self._flush_to_disk()

    # Others
    def display(self) -> None:
        """Pretty print Configuration block."""
        assert self.loaded
        io.console.print_header("Configuration display")
        io.console.print_section(f"Scope: {str(self._descriptor.scope).upper()}")
        io.console.print_section(f"Path: {self._descriptor.path}")
        io.console.print_section("Details:")

        io.console.print(self._flush())

    def validate(self) -> None:
        """Validate a Config against it's shema."""
        assert self.loaded
        self._check()

    def to_str(self) -> str:
        """Get configuration as str."""
        return self._flush()

    def from_str(self, raw: str) -> None:
        """Set configuration from str."""
        self._load(raw)


@typechecked
class YmlConfigFile(ConfigFile):

    def __init__(self, config_desc: ConfigDesc):
        """Initialize a configuration file representation."""
        assert config_desc.kind != ConfigKind.PLUGIN
        self._details: dict = {}
        super().__init__(config_desc)

    # Private unguarded functions

    # Overrides of super methods
    def _check(self) -> None:
        """Validate a config according to its scheme."""
        super()._check()
        ValidationScheme(str(self._descriptor.kind).lower()).validate(
            self._details, filepath=self._descriptor.path.name
        )

    def _load(self, raw: str) -> None:
        super()._load(raw)
        self._str_to_yml()

    def _flush(self) -> str:
        self._yml_to_str()
        return super()._flush()

    # str -> yml and yml -> str conversion
    def _str_to_yml(self) -> None:
        self._details = YAML(typ="safe").load(StringIO(self._raw))

    def _yml_to_str(self) -> None:
        yml = YAML(typ="safe")
        yml.default_flow_style = False
        yml.indent = 4
        str_stream = StringIO()
        yml.dump(self._details, str_stream)
        self._raw = str_stream.getvalue()
        str_stream.close()

    # Public safe functions

    # IO from obj
    def from_dict(self, d: dict) -> None:
        """Fill the config from the raw parameter."""
        self._details = d
        self._flush()
        self._check()

    def to_dict(self) -> dict:
        """Convert the Config() to regular dict."""
        assert self.loaded
        return self._details.copy()

    # Others
    @property
    def config(self) -> Config:
        """Get config object associated with config file."""
        return Config(self._details)


@typechecked
class Profile(YmlConfigFile):
    """A profile represents the most complete object the user can provide.

    It is built upon 5 configuration, one of each kind
    (compiler, runtime, machine, criterion & group) and plugins
    and gathers all required information to start a validation process. A
    profile object is the basic representation to be manipulated by the user.
    """

    CONFIGS_KINDS = [
        ConfigKind.COMPILER,
        ConfigKind.CRITERION,
        ConfigKind.GROUP,
        ConfigKind.MACHINE,
        ConfigKind.RUNTIME,
    ]

    def __init__(self, config_desc: ConfigDesc, cl: ConfigLocator | None = None):
        """Initialize a profile."""
        assert config_desc.kind == ConfigKind.PROFILE
        self._config_locator = cl if cl is not None else ConfigLocator()
        self._innerconfigs: dict[ConfigKind, YmlConfigFile] = {}
        super().__init__(config_desc)

    def _load_sub_configs(self) -> None:
        assert self.loaded
        for kind in Profile.CONFIGS_KINDS:
            user_token: str = super().config[str(kind).lower()]
            if user_token == "":
                user_token = f"{str(ConfigScope.GLOBAL)}:default"

            cd: ConfigDesc = self._config_locator.parse_full_raise(
                user_token, kind=kind, should_exist=True
            )
            c: YmlConfigFile = YmlConfigFile(cd)
            self._innerconfigs[kind] = c

    def _check(self) -> None:
        super()._check()
        for kind in Profile.CONFIGS_KINDS:
            self._innerconfigs[kind].validate()

    def _load(self, raw: str) -> None:
        """Load a profile from disk."""
        super()._load(raw)
        self._load_sub_configs()

    @property
    def compiler(self) -> Config:
        """Access the 'compiler' section.

        :return: the 'compiler' dict segment
        :rtype: dict
        """
        return self._innerconfigs[ConfigKind.COMPILER].config

    @property
    def criterion(self) -> Config:
        """Access the 'criterion' section.

        :return: the 'criterion' dict segment
        :rtype: dict
        """
        return self._innerconfigs[ConfigKind.CRITERION].config

    @property
    def group(self) -> Config:
        """Access the 'group' section.

        :return: the 'group' dict segment
        :rtype: dict
        """
        return self._innerconfigs[ConfigKind.GROUP].config

    @property
    def machine(self) -> Config:
        """Access the 'machine' section.

        :return: the 'machine' dict segment
        :rtype: dict
        """
        return self._innerconfigs[ConfigKind.MACHINE].config

    @property
    def runtime(self) -> Config:
        """Access the 'runtime' section.

        :return: the 'runtime' dict segment
        :rtype: dict
        """
        return self._innerconfigs[ConfigKind.RUNTIME].config


STD_CONFIG_KINDS = [
    ConfigKind.COMPILER,
    ConfigKind.CRITERION,
    ConfigKind.GROUP,
    ConfigKind.MACHINE,
    ConfigKind.RUNTIME,
]


@typechecked
def get_conf(cd: ConfigDesc) -> ConfigFile:
    """Get Appropriate ConfigFile Object."""
    assert cd is not None
    if cd.kind == ConfigKind.PROFILE:
        return Profile(cd)
    if cd.kind in STD_CONFIG_KINDS:
        return YmlConfigFile(cd)
    return ConfigFile(cd)
