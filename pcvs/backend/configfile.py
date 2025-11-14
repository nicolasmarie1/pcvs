import os
from io import StringIO

import click
from ruamel.yaml import YAML

from pcvs import io
from pcvs.backend.config import Config
from pcvs.helpers.storage import ConfigDesc
from pcvs.helpers.storage import ConfigKind
from pcvs.helpers.validation import ValidationScheme


class ConfigFile:
    """
    Handle the basic configuration block.

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
        self._details = None
        assert config_desc.kind != ConfigKind.PLUGIN
        if self.exist:
            self._load_from_disk()
            self._check()

    # Private unguarded functions
    def _check(self) -> None:
        """Validate a config according to its scheme."""
        ValidationScheme(self._descriptor.kind).validate(
            self._details, filepath=self._descriptor.path
        )

    def _load_from_disk(self) -> None:
        with open(self._descriptor.path, encoding="utf-8") as f:
            self._details = YAML(typ="safe").load(f)

    def _flush_to_disk(self) -> None:
        # create dir if it does not exist
        self._descriptor.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._descriptor.path, "w", encoding="utf-8") as f:
            yml = YAML(typ="safe")
            yml.default_flow_style = False
            yml.dump(self._details, f)

    # Public safe functions

    # Property for Disk Loading & ObjectFilling choerency management.
    @property
    def exist(self) -> bool:
        """Return if the config file exist on disk."""
        return self._descriptor.exist

    @property
    def loaded(self) -> bool:
        """Return if the config is loaded in Object."""
        return self._details is not None

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
        """Write the configuration block to disk."""
        assert self.loaded
        self._check()
        self._flush_to_disk()

    def delete(self) -> None:
        """Delete a configuration block from disk."""
        assert self.exist
        io.console.info(
            f"Remove {self._descriptor.name} from '{self._descriptor.kind} ({self._descriptor.scope})'"
        )
        os.remove(self._descriptor.path)

    def edit(self) -> None:
        """Open the current block for edition.

        :raises Exception: Something occurred on the edited version.
        """
        assert self.exist

        with open(self._descriptor.path, "r", encoding="utf-8") as fh:
            stream = fh.read()

        edited_stream = click.edit(
            stream, extension=ConfigKind.get_filetype(self._descriptor.kind), require_save=True
        )
        if edited_stream is not None:
            edited_yaml = YAML(typ="safe").load(edited_stream)
            self._details = edited_yaml
            self._check()
            self._flush_to_disk()

    # IO from obj
    def from_dict(self, d: dict) -> None:
        """Fill the config from the raw parameter."""
        self._details = d
        self._check()

    def to_dict(self) -> dict:
        """Convert the Config() to regular dict."""
        assert self.loaded
        return self._details.copy()

    # Others
    def display(self) -> None:
        """Pretty print Configuration block."""
        assert self.loaded
        io.console.print_header("Configuration display")
        io.console.print_section(f"Scope: {str(self._descriptor.scope).upper()}")
        io.console.print_section(f"Path: {self._descriptor.path}")
        io.console.print_section("Details:")

        yml = YAML()
        yml.default_flow_style = False
        yml.indent = 4
        string_stream = StringIO()
        yml.dump(self._details, string_stream)
        output_str = string_stream.getvalue()
        string_stream.close()
        io.console.print(output_str)

    def validate(self) -> None:
        """Validate a Config against it's shema."""
        assert self.loaded
        self._check()

    @property
    def config(self) -> None:
        """Get config object associated with config file."""
        return Config(self._details)
