import enum
import importlib
import inspect
import os
import pkgutil
import sys
from abc import abstractmethod
from types import ModuleType
from typing import Any

from pcvs import io
from pcvs.helpers.exceptions import PluginException


class Plugin:
    """
    Base class to inherit from when implementing a plugin.

    This class should be used by any defined plugin and:

    * the attribute ``step`` should be set to a possible value defined by
      :class:`Plugin.Step`.
    * implement the function ``run(self, *args, **kwargs)``

    List of possible values is defined by the per-step API.

    :raises PluginException.NotImplementedError: if run() method is not overridden
    """

    class Step(enum.Enum):
        """Possible pass a plugin can be loaded into.

        ``*_EVAL`` steps describe plugin passes where the function outcome can
        infer with the actual workflow.
        """

        INVALID = -1
        START_BEFORE = enum.auto()
        START_AFTER = enum.auto()
        TFILE_BEFORE = enum.auto()
        TDESC_BEFORE = enum.auto()
        TEST_EVAL = enum.auto()
        TDESC_AFTER = enum.auto()
        TFILE_AFTER = enum.auto()
        SCHED_BEFORE = enum.auto()
        SCHED_SET_BEFORE = enum.auto()
        SCHED_SET_EVAL = enum.auto()
        SCHED_JOB_EVAL = enum.auto()
        SCHED_SET_AFTER = enum.auto()
        TEST_RESULT_EVAL = enum.auto()
        SCHED_PUBLISH_BEFORE = enum.auto()
        SCHED_PUBLISH_WRITE = enum.auto()
        SCHED_PUBLISH_AFTER = enum.auto()
        SCHED_AFTER = enum.auto()
        END_BEFORE = enum.auto()
        END_AFTER = enum.auto()

        def __str__(self) -> str:
            """Stringify a Step as a printable string

            :return: a printable string according to the step
            :rtype: str
            """
            return self.name

    step = Step.INVALID

    def __init__(self) -> None:
        """constructor method."""
        self._type = type(self)

    @abstractmethod
    def run(self, *args, **kwargs):  # type: ignore
        """To-be-overridden method."""
        raise PluginException.NotImplementedError(str(type(self)))


class Collection:
    """The Plugin Manager.

    Consists in a dict of passes, eaching being initialized to None. Only one
    plugin can be set to a given step (the last loaded).
    """

    def __init__(self) -> None:
        """constructor method"""
        self._plugins: dict[Plugin.Step, dict[str, Any]] = {step: {} for step in list(Plugin.Step)}
        self._enabled: dict[Plugin.Step, Any] = {step: None for step in list(Plugin.Step)}

    def register_default_plugins(self) -> None:
        """Detect plugins stored in default places."""
        try:
            self.register_plugin_by_package("pcvs.plugins.default", activate=True)
            self.register_plugin_by_package("pcvs.plugins.contrib")
            self.register_plugin_by_package("pcvs.config.plugin")
        except Exception as e:
            raise PluginException("Error while registering plugin.") from e

    def exist_plugin(self, name: str) -> bool:
        """Check if a plugin already exist."""
        for _, plugins in self._plugins.items():
            for plname, _ in plugins.items():
                if name.lower() == plname:
                    return True
        return False

    def activate_plugin(self, name: str) -> None:
        """Flag a plugin as active, meaning it will be called when the pass is
        reached.

        :param name: the plugin name.
        :type name: str"""
        for _, plugins in self._plugins.items():
            for plname, plugin in plugins.items():
                if name.lower() == plname:
                    io.console.debug("Activate plugin: '{}'".format(name))
                    if self._enabled[plugin.step]:
                        io.console.debug(" -> overrides {}".format(self._enabled[plugin.step]))
                    self._enabled[plugin.step] = plugin
                    return
        io.console.warn("Unable to find a plugin named '{}'".format(name))

    def invoke_plugins(self, step: Plugin.Step, method: str = "run", *args, **kwargs):  # type: ignore
        """Load the appropriate plugin, given a step

        :param step: the step to target
        :type step: :class:`Plugin.Step`
        :raises PluginException.BadStepError: wrong Step value
        :return: the same return value as returned by the ``run()`` plugin method.
        :rtype: Any
        """
        if step not in list(Plugin.Step):
            raise PluginException.BadStepError(f"Invalid step: '{step}'")

        if self._enabled[step]:
            assert method
            if not hasattr(self._enabled[step], method):
                raise PluginException(
                    f"Can't find method '{method}' in plugin '{self._enabled[step]}'."
                )
            func = getattr(self._enabled[step], method)
            return func(*args, **kwargs)

        return None

    def has_enabled_step(self, step: Plugin.Step, method: str = "run") -> bool:
        """Check if a given pass is enabled.

        :param step: the pass
        :type step: :class:`Step`
        :return: True if defined, False otherwise
        :rtype: bool
        """
        if self._enabled[step] is None:
            return False
        if not hasattr(self._enabled[step], method):
            return False
        return True

    def try_invoke_plugins(self, step: Plugin.Step, method: str = "run", *args, **kwargs):  # type: ignore
        if self.has_enabled_step(step, method):
            return self.invoke_plugins(step, method, *args, **kwargs)

    def nb_plugins_for(self, step: Plugin.Step) -> int:
        """Count the number of possible plugins for a given step.

        :param step: the step to check
        :type step: str

        :return: the number of plugins
        :rtype: int"""
        if step not in self._plugins:
            return -1

        return len(self._plugins[step])

    def show_plugins(self) -> None:
        """Display plugin context to stdout."""
        for step, elements in self._plugins.items():
            if len(elements) > 0:
                io.console.print_section("Step {}:".format(str(step)))
                for name, module in elements.items():
                    io.console.print_item(f"{name}/{type(module).__name__}")

    def show_enabled_plugins(self) -> None:
        """Display the list of loaded plugins."""
        empty = True
        for step, e in self._enabled.items():
            if e:
                empty = False
                io.console.print_item("{}: {}".format(str(step), type(e).__name__))

        if empty:
            io.console.print_item("None")

    def register_plugin_by_file(self, modpath: str, activate: bool = False) -> None:
        """Based on a filepath (as a module dir), load plugins contained in it.

        :param modpath: valid python filepath
        :type modpath: str
        """
        io.console.debug(f"Registering plugin by path: {modpath}")
        # the content is added to "pcvs-contrib" module
        spec = importlib.util.spec_from_file_location("contrib", modpath)
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        self.register_plugin_by_module(str(mod), mod, activate)

    def register_plugin_by_module(self, name: str, mod: ModuleType, activate: bool = False) -> None:
        """Based on a module name, load any defined plugin.

        mod must be a valid PYTHON module name.

        :param mod: module name
        :type mod: str
        """
        for _, the_class in inspect.getmembers(mod, inspect.isclass):
            if issubclass(the_class, Plugin) and the_class is not Plugin:
                step_str = str(the_class.step)
                if self.exist_plugin(name):
                    io.console.critical(f"A plugin with the name {name} is already register.")
                io.console.debug(f"Registering plugin '{name}' by module '{mod}' ({step_str})")
                self._plugins[the_class.step][name] = the_class()
                if activate:
                    self.activate_plugin(name)

    def register_plugin_by_dir(self, pkgpath: str, activate: bool = False) -> None:
        """From a prefix directory, load any plugin defined in it.

        Mainly used to load any Plugin classes defined in a directory. The
        directory must be layout'd as a PYTHON package.

        :param pkgpath: prefix path
        :type pkgpath: str
        """
        path = os.path.join(os.path.abspath(pkgpath), "..")
        pkgname = os.path.basename(pkgpath)

        sys.path.insert(0, path)
        self.register_plugin_by_package(pkgname, activate)
        sys.path.remove(path)

    def register_plugin_by_package(self, pkgname: str, activate: bool = False) -> None:
        """Based on a package name, load any plugin defined into it.

        :param pkgname: package name, valid under current PYTHON env.
        :type pkgname: str
        :raises PluginException.LoadError: Error while importing the package
        """
        mod = importlib.import_module(pkgname)
        for _, name, _ in pkgutil.iter_modules(mod.__path__, mod.__name__ + "."):
            try:
                submod = importlib.import_module(name)
                self.register_plugin_by_module(name.split(".")[-1], submod, activate)
            except Exception as e:
                raise PluginException.LoadError(name) from e
