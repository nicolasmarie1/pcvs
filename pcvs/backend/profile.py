"""Profile Config File representation."""

from pcvs.backend.config import Config
from pcvs.backend.configfile import ConfigFile
from pcvs.helpers.storage import ConfigDesc
from pcvs.helpers.storage import ConfigKind
from pcvs.helpers.storage import ConfigLocator


class Profile(ConfigFile):
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

    def __init__(self, config_desc: ConfigDesc, cl: ConfigLocator = None):
        """Initialize a profile."""
        assert config_desc.kind == ConfigKind.PROFILE
        self._config_locator = cl if cl is not None else ConfigLocator()
        self._innerconfigs: dict[str, ConfigFile] = {}
        super().__init__(config_desc)

    def _load_sub_configs(self):
        assert self.loaded
        for kind in Profile.CONFIGS_KINDS:
            user_token: str = super().config[str(kind)]
            cd: ConfigDesc = self._config_locator.parse_full_user_token(
                user_token, kind=kind, should_exist=True
            )
            c: ConfigFile = ConfigFile(cd)
            self._innerconfigs[kind] = c

    def _check(self):
        super()._check()
        for kind in Profile.CONFIGS_KINDS:
            self._innerconfigs[kind].validate()

    def _load_from_disk(self) -> None:
        """Load a profile from disk."""
        super()._load_from_disk()
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
