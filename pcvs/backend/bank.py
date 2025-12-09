import os
import tarfile
import tempfile
from typing import Any

from ruamel.yaml import YAML
from typeguard import typechecked

from pcvs import dsl
from pcvs import io
from pcvs import PATH_BANK
from pcvs.helpers import git
from pcvs.helpers import utils
from pcvs.helpers.exceptions import BankException
from pcvs.helpers.exceptions import CommonException
from pcvs.orchestration.publishers import BuildDirectoryManager


@typechecked
class Bank(dsl.Bank):
    """Representation of a PCVS result datastore.

    Stored as a Git repo, a bank hold multiple results to be scanned and used to
    analyse benchmarks result over time. A single bank can manipulate namespaces
    (referred as 'projects'). The namespace is provided by suffixing ``@proj``
    to the original name.

    :param root: the root bank directory
    :type root: str
    :param repo: the Pygit2 handle
    :type repo:  :class:`Pygit2.Repository`
    :param config: when set, configuration file of the just-submitted archive
    :type config: : dict
    :param rootree: When set, root handler to the next commit to insert
    :type rootree: :class:`Pygit2.Object`
    :param locked: Serialize Bank manipulation among multiple processes
    :type locked: bool
    :param proj_name: extracted default-proj from initial token
    :type proj_name: str
    """

    def __init__(self, token: str) -> None:
        """Build a Bank.

        A Bank is describe by an optional token follow by a bank name or bank path.

        Example: ``cholesky@mpc_ci_bank``, ``nas@/home/mpc/mpc_ci_bank``

        :param token: name, path, project@name or project@path
        :type token: str
        """
        # Search for the Bank
        path_or_name: str = token
        dflt_proj: str = "default"
        # split name/path & default-proj from token
        array: list[str] = token.split("@", 1)
        if len(array) > 1:
            dflt_proj = array[0]
            path_or_name = array[1]

        # by name
        banks = list_banks()
        if path_or_name in banks:
            name = path_or_name
            path = banks[path_or_name]
        # by paths
        elif path_or_name in banks.values():
            for k, v in banks.items():
                if v == path_or_name:
                    name = k
                    break
            path = path_or_name
        # by unregistered existing path
        elif os.path.isdir(path_or_name):
            io.console.warning(f"Loading unregistered Bank from: '{path_or_name}'")
            path = path_or_name
            name = os.path.basename(path_or_name)
        # We did not found the bank.
        else:
            raise BankException.NotFoundError(f"Unable to find bank: '{path_or_name}'")

        self._dflt_proj: str = dflt_proj
        self._name: str = name
        self._path: str = path

        super().__init__(self._path, self._dflt_proj)

    @property
    def default_project(self) -> str:
        """
        Get the default project select at the bank creation.

        Return 'default' when no default project are specify at bank creation.

        :return: the project name (as a Ref branch)
        :rtype: str
        """
        return self._dflt_proj

    @property
    def prefix(self) -> str | None:
        """
        Get path to bank directory.

        :return: absolute path to directory
        :rtype: str
        """
        return self._path

    @property
    def name(self) -> str:
        """
        Get bank name.

        :return: the bank name
        :rtype: str
        """
        return self._name

    def __str__(self) -> str:
        """Stringification of a bank.

        :return: a combination of name & path
        :rtype: str
        """
        return str({self._name: self._path})

    def show(self, stringify: bool = False) -> str | None:
        """Print the bank on stdout.

        .. note::
            This function does not use :class:`log.IOManager`

        :param stringify: if True, a string will be returned. Print on stdout
            otherwise
        :type stringify: bool
        :return: str if stringify is True, Nothing otherwise`
        """
        string = ["Projects contained in bank '{}':".format(self._path)]
        # browse references
        for project, series in self.list_all().items():
            string.append("- {:<8}: {} distinct testsuite(s)".format(project, len(series)))
            for s in series:
                string.append("  * {}: {} run(s)".format(s.name, len(s)))

        if stringify:
            return "\n".join(string)
        else:
            print("\n".join(string))
            return None

    def __del__(self) -> None:
        """
        Close / disconnect a bank (releasing lock)
        """
        self.disconnect()

    def save_from_hdl(
        self, target_project: str | None, hdl: BuildDirectoryManager, msg: str | None = None
    ) -> None:
        """
        Create a new node into the bank for the given project, based on result handler.

        :param target_project: valid project (=branch)
        :type target_project: str
        :param hdl: the result build directory handler
        :type hdl: BuildDirectoryManager
        :param msg: the custom message to attach to this run (=commit msg)
        :type msg: str, optional
        """
        if target_project is None:
            target_project = self.default_project
        series = self.get_series(target_project)
        if series is None:
            series = self.new_series(target_project)

        run = dsl.Run(from_series=series)
        metadata: dict[str, Any] = {"cnt": {}}

        for job in hdl.results.browse_tests():
            metadata["cnt"].setdefault(str(job.state), 0)
            metadata["cnt"][str(job.state)] += 1
            run.update(job.name, job.to_json())

        self.set_id(
            an=hdl.config["validation"]["author"]["name"],
            am=hdl.config["validation"]["author"]["email"],
            cn=git.get_current_username(),
            cm=git.get_current_usermail(),
        )

        run.update(".pcvs-cache/conf.json", hdl.config.to_dict())

        series.commit(
            run,
            metadata=metadata,
            msg=msg,
            timestamp=int(hdl.config["validation"]["datetime"].timestamp()),
        )

    def save_from_buildir(self, tag: str | None, buildpath: str, msg: str | None = None) -> None:
        """Extract results from the given build directory & store into the bank.

        :param tag: overridable default project (if different)
        :type tag: str
        :param buildpath: the directory where PCVS stored results
        :type buildpath: str
        :param msg: the custom message to attach to this run (=commit msg)
        :type msg: str, optional
        """
        hdl = BuildDirectoryManager(buildpath)
        hdl.load_config()
        hdl.init_results()

        self.save_from_hdl(tag, hdl, msg)

    def save_from_archive(self, tag: str, archivepath: str, msg: str | None = None) -> None:
        """Extract results from the archive, if used to export results.

        This is basically the same as :func:`BanK.save_from_buildir` except
        the archive is extracted first.

        :param tag: overridable default project (if different)
        :type tag: str
        :param archivepath: archive path
        :type archivepath: str
        :param msg: the custom message to attach to this run (=commit msg)
        :type msg: str, optional
        """
        assert os.path.isfile(archivepath)

        with tempfile.TemporaryDirectory() as tarpath:
            tarfile.open(os.path.join(archivepath)).extractall(tarpath)
            d = [x for x in os.listdir(tarpath) if x.startswith("pcvsrun_")]
            assert len(d) == 1
            self.save_from_buildir(tag, os.path.join(tarpath, d[0]), msg=msg)

    def save_new_run_from_instance(
        self, target_project: str | None, hdl: BuildDirectoryManager, msg: str | None = None
    ) -> None:
        self.save_from_hdl(target_project, hdl, msg)

    def save_new_run(self, target_project: str, path: str) -> None:
        """
        Store a new run to the current bank.

        :param target_project: the target branch name
        :type target_project: str
        :param path: the target archive or build dir to store.
        :type path: str
        :raises NotPCVSRelated: the path pointing to a valid
            PCVS run.
        """
        if not utils.check_is_build_or_archive(path):
            raise CommonException.NotPCVSRelated(
                reason="Invalid path, not PCVS-related", dbg_info={"path": path}
            )

        if utils.check_is_archive(path):
            # convert to prefix
            # update path according to it
            hdl = BuildDirectoryManager.load_from_archive(path)
        else:
            hdl = BuildDirectoryManager(build_dir=path)
            hdl.load_config()

        self.save_new_run_from_instance(target_project, hdl)

    def __repr__(self) -> str:
        """Bank representation.

        :return: a dict-based representation
        :rtype: dict
        """
        return repr({"rootpath": self._path, "name": self._name})

    def get_count(self) -> int:
        """
        Get the number of projects managed by this bank handle.

        :return: number of projects
        :rtype: int
        """
        return len(self.list_projects())


@typechecked
def init_banklink(name: str, path: str) -> bool:
    """
    Create a new bank and store it to the global system.

    :param name: bank label
    :type name: str
    :param path: path to bank directory
    :type path: str
    :return: if bank was successfully created
    :rtype: bool
    """
    banks = list_banks()
    # check if the bank name already exist
    if name in banks:
        return False
    # trying to import a bank that already exist with an other name
    if path in banks.values():
        return False

    # check if the folder of the bank can be created
    # allow already existing bank to be reimported
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return False

    # register bank name/path in pcvs home configuration
    banks[name] = path
    write_banks(banks)

    # create the bank
    b = Bank(name)
    b.connect()

    return True


@typechecked
def rm_banklink(name: str) -> None:
    """Remove a bank from the global management system.

    :param name: bank name
    :type name: str
    """
    banks = list_banks()
    banks.pop(name)
    write_banks(banks)


@typechecked
def list_banks() -> dict:
    """Read Banks."""
    banks = {}
    try:
        with open(PATH_BANK, "r", encoding="utf-8") as f:
            banks = YAML(typ="safe").load(f)
    except FileNotFoundError:
        # nothing to do, file may not exist
        pass
    return banks


@typechecked
def write_banks(banks: dict[str, str]) -> None:
    """Write banks."""
    try:
        prefix_file = os.path.dirname(PATH_BANK)
        if not os.path.isdir(prefix_file):
            os.makedirs(prefix_file, exist_ok=True)
        with open(PATH_BANK, "w+", encoding="utf-8") as f:
            YAML(typ="safe").dump(banks, f)
    except IOError as e:
        raise BankException.IOError("Fail to write banks list to disk.") from e
