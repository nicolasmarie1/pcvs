"""Helper package to find configuration and plugin files in pcvs configuration directories."""

import os
from enum import Enum
from pathlib import Path

from pcvs import io
from pcvs import NAME_CONFIGDIR
from pcvs import PATH_HOMEDIR
from pcvs import PATH_INSTDIR

try:
    import rich_click as click

    click.rich_click.SHOW_ARGUMENTS = True
except ImportError:
    import click


class ConfigScope(Enum):
    """
    Storage Scope Enumeration.

    :var GLOBAL: pcvs installation path
    :var USER: user Home directory
    :var REPO: current .git repo
    :var LOCAL: current testing directory
    :var CWD: current working directory
    :var ABS: user provided absolute path
    """

    GLOBAL = 0
    USER = 1
    LOCAL = 2

    def __str__(self):
        """Convert to str."""
        return ConfigScope.tostr(self)

    def __repr__(self):
        """Convert to str."""
        return ConfigScope.tostr(self)

    @classmethod
    def tostr(cls, ct) -> str:
        """Get subpath from ConfigType."""
        scope_to_str = {
            ConfigScope.GLOBAL: "global",
            ConfigScope.USER: "user",
            ConfigScope.LOCAL: "local",
        }
        return scope_to_str[ct]

    @classmethod
    def fromstr(cls, scope: str):
        """Get Scope from user str."""
        str_to_scope = {
            "global": ConfigScope.GLOBAL,
            "user": ConfigScope.USER,
            "local": ConfigScope.LOCAL,
        }
        return str_to_scope.get(scope.lower(), None)

    @classmethod
    def all_scopes(cls) -> list:
        """Get all possible scopes."""
        return [
            ConfigScope.LOCAL,
            ConfigScope.USER,
            ConfigScope.GLOBAL,
        ]


class ConfigKind(Enum):
    """
    Configuration types.

    Associated with their config subdirectory and their default extension.
    """

    PROFILE = 0
    COMPILER = 1
    RUNTIME = 2
    MACHINE = 3
    CRITERION = 4
    GROUP = 5
    PLUGIN = 6

    def __str__(self):
        """Convert to str."""
        return ConfigKind.tostr(self)

    def __repr__(self):
        """Convert to str."""
        return ConfigKind.tostr(self)

    @classmethod
    def tostr(cls, ct) -> str:
        """Get subpath from ConfigType."""
        kind_to_str = {
            ConfigKind.PROFILE: "profile",
            ConfigKind.COMPILER: "compiler",
            ConfigKind.RUNTIME: "runtime",
            ConfigKind.MACHINE: "machine",
            ConfigKind.CRITERION: "criterion",
            ConfigKind.GROUP: "group",
            ConfigKind.PLUGIN: "plugin",
        }
        return kind_to_str[ct]

    @classmethod
    def fromstr(cls, kind: str):
        """Get Scope from user str."""
        str_to_kind = {
            "profile": ConfigKind.PROFILE,
            "compiler": ConfigKind.COMPILER,
            "runtime": ConfigKind.RUNTIME,
            "machine": ConfigKind.MACHINE,
            "criterion": ConfigKind.CRITERION,
            "group": ConfigKind.GROUP,
            "plugin": ConfigKind.PLUGIN,
        }
        return str_to_kind.get(kind.lower(), None)

    @classmethod
    def all_kinds(cls) -> list:
        """Get a list of all ConfigTypes."""
        return [
            ConfigKind.PROFILE,
            ConfigKind.COMPILER,
            ConfigKind.CRITERION,
            ConfigKind.GROUP,
            ConfigKind.MACHINE,
            ConfigKind.RUNTIME,
            ConfigKind.PLUGIN,
        ]

    @classmethod
    def get_filetype(cls, ct) -> str:
        """Get file type from ConfigType."""
        config_extensions = {
            ConfigKind.PROFILE: ".yml",
            ConfigKind.COMPILER: ".yml",
            ConfigKind.RUNTIME: ".yml",
            ConfigKind.MACHINE: ".yml",
            ConfigKind.CRITERION: ".yml",
            ConfigKind.GROUP: ".yml",
            ConfigKind.PLUGIN: ".py",
        }
        return config_extensions[ct]


class ConfigDesc:
    """An object to describe a config file."""

    def __init__(self, name: str, path: str, kind: ConfigKind, scope: ConfigScope):
        """Initialize a Config file object description."""
        self._name: str = name
        self._path: Path = path
        self._kind: ConfigKind = kind
        self._scope: ConfigScope = scope

    @property
    def name(self):
        """The name of the config (with file extension)."""
        return self._name

    @property
    def path(self):
        """The path of the config."""
        return self._path

    @property
    def kind(self):
        """The type of the config."""
        return self._kind

    @property
    def scope(self):
        """The scope of the config."""
        return self._scope

    @property
    def full_name(self):
        """Get the full name of the config."""
        return ":".join([str(self._scope), str(self._kind), self._name])

    @property
    def exist(self):
        """Return if the file pointer by this config descriptor exist."""
        return self._path.is_file()


class ConfigLocator:
    """Helper to find and list config."""

    EXEC_PATH: str

    @classmethod
    def __get_local_path(cls, path: str, subpath: str = NAME_CONFIGDIR) -> str:
        cur = path
        parent = "/"
        while not os.path.isdir(os.path.join(cur, subpath)):
            parent = os.path.dirname(cur)
            # Reach '/' and not found
            if parent == cur:
                cur = path
                break
            cur = parent
        # if we are in home dir, correct path is current working dir
        if cur == PATH_HOMEDIR:
            cur = path
        return os.path.join(cur, subpath)

    def __init__(self):
        """Init a Config Locator."""
        rel_exec_path = os.path.abspath(self.EXEC_PATH if self.EXEC_PATH else os.getcwd())
        self._storage_scope_paths: dict[ConfigScope, Path] = {
            ConfigScope.GLOBAL: Path(PATH_INSTDIR).joinpath("config"),
            ConfigScope.USER: Path(PATH_HOMEDIR),
            ConfigScope.LOCAL: Path(self.__get_local_path(rel_exec_path)),
        }

    def parse_scope_and_kind_user_token(
        self,
        user_token: str,
    ) -> (ConfigScope, ConfigKind):
        """Parse scope[:kind] token, raise on failure."""
        desc, error = self.parse_scope_and_kind(user_token)
        if desc is None:
            io.console.error(error)
            raise click.BadArgumentUsage(error)
        return desc

    def parse_scope_and_kind(
        self, user_token: str, default_kind: ConfigKind = None
    ) -> ((ConfigScope, ConfigKind), str):
        """Parse scope[:kind] token, return None on failure."""
        token = user_token.split(":")
        if len(token) == 1:
            scope, kind = ConfigScope.fromstr(token[0]), default_kind
            if scope is None:
                scope, kind = None, ConfigKind.fromstr(token[0])
                if kind is None:
                    return (
                        None,
                        f"Invalid scope or kind, got '{user_token}', "
                        f"valid scope are: {ConfigScope.all_scopes()} "
                        f"and valid kind are: '{ConfigKind.all_kinds()}'",
                    )
                if default_kind is not None and kind != default_kind:
                    return (
                        None,
                        f"Invalude kind, '{kind}' specify, needs '{default_kind}', in '{user_token}'",
                    )
            return ((scope, kind), None)
        if len(token) == 2:
            scope, kind = ConfigScope.fromstr(token[0]), ConfigKind.fromstr(token[1])
            if scope is None:
                return (
                    None,
                    f"Invalid config scope, got '{token[0]}', valid scopes are: {ConfigScope.all_scopes()}",
                )
            if kind is None:
                return (
                    None,
                    f"Invalid config kind, got '{token[1]}', valid kinds are: {ConfigKind.all_kinds()}",
                )
            if default_kind is not None and kind != default_kind:
                return (
                    None,
                    f"Invalude kind, '{kind}' specify, needs '{default_kind}', in '{user_token}'",
                )
            return ((scope, kind), None)
        return (None, f"Bad user token, token should be 'scope[:kind]', got '{user_token}'")

    def parse_full_user_token(
        self,
        user_token: str,
        kind: ConfigKind = None,
        should_exist: bool | None = None,
    ) -> ConfigDesc | None:
        """Parse use token and return and associated config file."""
        desc, error = self.parse_full(user_token, kind, should_exist)
        if desc is None:
            io.console.error(error)
            raise click.BadArgumentUsage(error)
        return desc

    def parse_full(
        self, user_token: str, pkind: ConfigKind, should_exist: bool
    ) -> (ConfigDesc | None, str):  # Config description and error
        """Parse [scope:[kind:]]label token."""
        # check for config scope & config kind
        scope = None
        kind = pkind
        token = user_token.split(":")
        if len(token) == 1:
            # config does not exist yet, but scope is not provided
            if should_exist is None or not should_exist:
                return (
                    None,
                    "For a configuration that may not exist, specifying a scope is mendatory, "
                    f"error parsing: '{user_token}'",
                )
            # kind not provided, neither by token nor by function
            if kind is None:
                return (None, f"Configuration kind not specify in user token: '{user_token}'.")
            file_name = Path(user_token)
        elif len(token) == 2 or len(token) == 3:
            desc, error = self.parse_scope_and_kind(":".join(token[:-1]), kind)
            if desc is None:
                return (None, error)
            scope, kind = desc
            if scope is None:
                if should_exist is None or not should_exist:
                    return (
                        None,
                        "For a configuration that may not exist, specifying a scope is mendatory, "
                        f"error parsing: '{user_token}'",
                    )
            if kind is None:
                return (None, f"Fail to parse kind from token '{user_token}'")
            file_name = Path(token[-1])
        else:
            return (None, f"Fail to parse scope (and kind), too many ':' in path '{user_token}'")

        assert kind is not None

        # check for missing extensions
        extension = ConfigKind.get_filetype(kind)
        if file_name.suffix != extension:
            io.console.warn(
                f"Adding missing suffix '{extension}' to file '{file_name}'->'{file_name.with_suffix(extension)}'"
            )
            file_name = file_name.with_suffix(extension)

        if should_exist is None:
            # May exist
            assert scope is not None

            # search for config
            config: ConfigDesc = self.find_config(file_name.name, kind, scope)
            if config is not None:
                return (config, None)
            config_path: Path = self.storage_path(file_name, kind, scope)
            cd: ConfigDesc = ConfigDesc(config_path.stem, config_path, kind, scope)
            return (cd, None)

        if should_exist:
            # searching for existing config
            config: ConfigDesc = self.find_config(file_name.name, kind, scope)
            if config is None:
                return (None, f"Config '{kind}:{file_name}' does not exist !")
            return (config, None)

        # should not exist
        assert scope is not None
        config_path: Path = self.storage_path(file_name, kind, scope)
        cd: ConfigDesc = ConfigDesc(config_path.stem, config_path, kind, scope)
        if cd.exist:
            return (None, f"Config, '{cd.full_name}' already exist !")
        return (cd, None)

    def storage_dir(self, scope: ConfigScope, kind: ConfigKind = None) -> Path:
        """Get config dir from config scope and config type."""
        assert scope is not None
        config_dir: Path = Path(self._storage_scope_paths[scope])
        if kind:
            config_dir = config_dir.joinpath(ConfigKind.tostr(kind))
        return config_dir

    def storage_path(self, file_name: str, kind: ConfigKind, scope: ConfigScope) -> Path:
        """Get config path from config label name, config type and config scope."""
        assert file_name is not None
        assert scope is not None
        config_path: Path = self.storage_dir(scope, kind).joinpath(file_name)
        return config_path

    def find_config(
        self, file_name: str, kind: ConfigKind, scope: ConfigScope = None
    ) -> ConfigDesc | None:
        """Get a config file description from it's name."""
        assert kind is not None
        scopes = ConfigScope.all_scopes() if scope is None else [scope]
        io.console.debug(
            f"Searching config for '{file_name}', of kind: '{kind}', in scopes: '{scopes}'"
        )
        for sc in scopes:
            config_path: Path = self.storage_path(file_name, kind, sc)
            io.console.debug(f"Looking for '{config_path}'.")
            if config_path.is_file() and config_path.suffix == ConfigKind.get_filetype(kind):
                io.console.debug(f"Found '{config_path}'.")
                return ConfigDesc(config_path.stem, config_path, kind, sc)
        return None

    def list_configs(self, kind: ConfigKind, scope: ConfigScope = None) -> list[ConfigDesc]:
        """List configs of type `ct` in scopes `cs`."""
        assert kind is not None
        scopes = ConfigScope.all_scopes() if scope is None else [scope]
        configs: list[ConfigDesc] = []
        for sc in scopes:
            configs_dir = self.storage_dir(sc, kind)
            for root, _, files in os.walk(configs_dir):
                for file in files:
                    config_path = Path(os.path.join(root, file))
                    if config_path.is_file() and config_path.suffix == ConfigKind.get_filetype(
                        kind
                    ):
                        configs.append(ConfigDesc(config_path.stem, config_path, kind, sc))
        return configs

    def list_all_configs(self, scope: ConfigScope = None) -> list[ConfigDesc]:
        """List all configs types in all scopes."""
        configs: list[ConfigDesc] = []
        for ct in ConfigKind.all_kinds():
            configs += self.list_configs(ct, scope)
        return configs


def set_exec_path(exec_path: str) -> None:
    """Set EXEC_PATH."""
    ConfigLocator.EXEC_PATH = exec_path
