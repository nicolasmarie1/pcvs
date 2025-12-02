from abc import ABC
from abc import abstractmethod


class PManager(ABC):
    """generic Package Manager"""

    def __init__(self, spec: str | None = None):
        """constructor for PManager object

        :param spec: specifications for this Package Manager, defaults to None
        :type spec: str, optional
        """

    @abstractmethod
    def get(self, load: bool, install: bool) -> str:
        """Get specified packages for this manager

        :param load: True to load the package
        :type load: bool
        :param install: True to install the package
        :type install: bool
        """

    @abstractmethod
    def install(self) -> None:
        """install specified packages"""


class SpackManager(PManager):
    """handles Spack package manager"""

    def __init__(self, spec: str):
        """constructor for SpackManager object

        :param spec: specifications for Spack manager
        :type spec: str
        """
        super().__init__(spec)
        self.spec = spec

    def get(self, load: bool = True, install: bool = True) -> str:
        """get the commands to install the specified package

        :param load: load the specified package, defaults to True
        :type load: bool, optional
        :param install: install the specified package, defaults to True
        :type install: bool, optional
        :return: command to install/load the package
        :rtype: str
        """
        s = list()
        if install:
            s.append("spack location -i {} > /dev/null 2>&1".format(self.spec))
            s.append('test "$?" != "0" && spack install {}'.format(self.spec))
        if load:
            s.append("eval `spack load --sh {}`".format(self.spec))
        return "\n".join(s)

    def install(self) -> None:
        """Load spack."""


class ModuleManager(PManager):
    """handles Module package manager"""

    def __init__(self, spec: str):
        """constructor for Module package manager

        :param spec: specifications for Module manager
        :type spec: str
        """
        super().__init__(spec)
        self.spec = spec

    def get(self, load: bool = True, install: bool = False) -> str:
        """get the command to install the specified package

        :param load: load the specified package, defaults to True
        :type load: bool, optional
        :param install: install the specified package, defaults to False
        :type install: bool, optional
        :return: command to install/load the package
        :rtype: str
        """
        s = ""
        # 'install' does not mean anything here
        if load:
            s += "module load {}".format(self.spec)
        return s

    def install(self) -> None:
        """Load module."""


def identify(pm_node: dict) -> list[PManager]:
    """identifies where

    :param pm_node: [description]
    :type pm_node: [type]
    :return: [description]
    :rtype: [type]
    """
    ret: list[PManager] = []
    if "spack" in pm_node:
        if not isinstance(pm_node["spack"], list):
            pm_node["spack"] = [pm_node["spack"]]
        for elt in pm_node["spack"]:
            ret.append(SpackManager(elt))

    if "module" in pm_node:
        if not isinstance(pm_node["module"], list):
            pm_node["module"] = [pm_node["module"]]
        for elt in pm_node["module"]:
            ret.append(ModuleManager(elt))
    return ret
