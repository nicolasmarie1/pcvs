import bz2
import datetime
import json
import os
import shutil
import tarfile
import tempfile
from bz2 import BZ2File
from typing import Any
from typing import Iterable
from typing import Optional
from typing import Self

from ruamel.yaml import YAML

import pcvs
from pcvs import io
from pcvs.backend.metaconfig import GlobalConfig
from pcvs.backend.metaconfig import MetaConfig
from pcvs.helpers import utils
from pcvs.helpers.exceptions import CommonException
from pcvs.helpers.exceptions import PublisherException
from pcvs.testing.test import Test
from pcvs.testing.teststate import TestState


class ResultFile:
    """
    A instance manages a pair of file dedicated to load/store PCVS job results
    on disk.

    A job result is stored in two different files whens given to a single
    ResultFile:
    * <prefix>.json, containing metadata (rc, command...)
    * <prefix>.bz2 BZ2-compressed job data.

    a MAGIC_TOKEN is used to detect file/data corruption.
    """

    MAGIC_TOKEN = "PCVS-START-RAW-OUTPUT"

    def __init__(self, filepath: str, filename: str):
        """
        Initialize a new pair of output files.

        :param filepath: path where files will be located.
        :type filepath: str
        :param filename: prefix filename
        :type filename: str
        """
        self._fileprefix: str = filename
        self._path: str = filepath
        self._cnt: int = 0
        self._sz: int = 0
        self._data: dict[str, Any] = {}

        prefix = os.path.join(filepath, filename)

        # R/W access & seek to the start of the file
        self._metadata_file = "{}.json".format(prefix)
        self._rawdata_file = "{}.bz2".format(prefix)

        try:
            if os.path.isfile(self._metadata_file):
                self.load()
        except Exception:
            pass

        # no way to have a bz2 be opened R/W at once ? seems not :(
        self._rawout: BZ2File | None = bz2.open(self._rawdata_file, "a")
        self._rawout_reader = bz2.open(self._rawdata_file, "r")

    def close(self) -> None:
        """
        Close the current instance (flush to disk)
        """
        self.flush()
        if self._rawout:
            self._rawout.close()
            self._rawout = None

    def flush(self) -> None:
        """
        Sync cache with disk
        """
        with open(self._metadata_file, "w") as fh:
            json.dump(self._data, fh)

        if self._rawout:
            self._rawout.flush()

    def save(self, job_id: str, data: dict[str, Any], output: bytes) -> None:
        """
        Save a new job to this instance.

        :param job_id: job id
        :type job_id: str
        :param data: metadata
        :type data: dict
        :param output: raw output
        :type output: bytes
        """
        assert isinstance(data, dict)
        assert "result" in data.keys()
        insert = {}
        start = 0
        length = 0
        if len(output) > 0:
            # we consider the raw cursor to always be at the end of the file
            # maybe lock the following to be atomic ?
            assert isinstance(self._rawout, BZ2File)
            start = self._rawout.tell()
            length = self._rawout.write(self.MAGIC_TOKEN.encode("utf-8"))
            length += self._rawout.write(output)

            insert = {"file": self.rawdata_prefix, "offset": start, "length": length}

        else:
            insert = {"file": "", "offset": -1, "length": 0}

        data["result"]["output"] = insert

        assert job_id not in self._data.keys()
        self._data[job_id] = data
        self._cnt += 1
        self._sz = max(start + length, self._sz + len(json.dumps(data)))

        if self._cnt % 10 == 0:
            self.flush()

    def load(self) -> None:
        """
        Load job data from disk to populate the cache.
        """
        with open(self._metadata_file, "r") as fh:
            # when reading metadata_file,
            # convert string-based keys to int (as managed by Python)
            content = json.load(fh)
            self._data = dict(content.items())

    @property
    def content(self) -> Iterable[Test]:
        for _, data in self._data.items():
            elt = Test()
            elt.from_json(data, self._metadata_file)

            offset = data["result"]["output"]["offset"]
            length = data["result"]["output"]["length"]
            if offset >= 0 and length > 0:
                # TODO: remove re-encode to re-decode later ...
                elt.encoded_output = self.extract_output(offset, length).encode("utf-8")
            yield elt

    def extract_output(self, offset: int, length: int) -> str:
        assert offset >= 0
        assert length > 0

        self._rawout_reader.seek(offset)
        rawout = self._rawout_reader.read(length).decode("utf-8")

        if not rawout.startswith(self.MAGIC_TOKEN):
            raise PublisherException.BadMagicTokenError("Internal Error.")
        return rawout[len(self.MAGIC_TOKEN) :]

    def retrieve_test(self, job_id: str | None = None, name: str | None = None) -> list[Test]:
        """
        Find jobs based on its id or name and return associated Test object.

        Only job_id OR name should be set (not both). To handle multiple matches,
        this function returns a list of class:`Test`.

        :param job_id: job id, defaults to None
        :type job_id: int, optional
        :param name: test name (full), defaults to None
        :type name: str, optional
        :return: A list of class:`Test`
        :rtype: list
        """
        if (job_id is None and name is None) or (job_id is not None and name is not None):
            raise PublisherException.UnknownJobError(f"{job_id}", name)

        lookup_table = []
        if job_id is not None:
            if job_id not in self._data:
                return []
            else:
                lookup_table = [self._data[job_id]]
        elif name is not None:
            lookup_table = list(filter(lambda x: name in x["id"]["fq_name"], self._data.values()))

        res = []
        for elt in lookup_table:
            offset = elt["result"]["output"]["offset"]
            length = elt["result"]["output"]["length"]
            rawout = ""
            if length > 0:
                assert elt["result"]["output"]["file"] in self.rawdata_prefix
                rawout = self.extract_output(offset, length)

            eltt = Test()
            eltt.from_json(elt, "internal, this should not fail")
            eltt.encoded_output = rawout.encode("utf-8")  # TODO: remove encode
            res.append(eltt)

        return res

    @property
    def size(self) -> int:
        """
        Current rawdata size

        :return: length of the rawdata file.
        :rtype: int
        """
        return self._sz

    @property
    def count(self) -> int:
        """
        Get the number of jobs in this handler.

        :return: job count
        :rtype: int
        """
        return self._cnt

    @property
    def prefix(self) -> str:
        """
        Getter to the build prefix

        :return: build prefix
        :rtype: str
        """
        return self._fileprefix

    @property
    def metadata_prefix(self) -> str:
        """
        Getter to the actual metadata file name

        :return: filename
        :rtype: str
        """
        return "{}.json".format(self._fileprefix)

    @property
    def rawdata_prefix(self) -> str:
        """
        Getter to the actual rawdata file name


        :return: file name
        :rtype: str
        """
        return "{}.bz2".format(self._fileprefix)

    def __repr__(self) -> str:
        return repr(self.__dict__)

    def __rich_repr__(self) -> Iterable[tuple[str, Any]]:
        return self.__dict__.items()


class ResultFileManager:
    """
    Manages multiple class:`ResultFile`. Main purpose is to manage files to
    ensure files stored on disk remain consistent.
    """

    increment = 0
    file_format = "jobs-{}"

    @classmethod
    def _ret_state_split_dict(cls) -> dict[str, list]:
        """
        initialize a default dict view with targeted statuses.

        :return: _description_
        :rtype: _type_
        """
        ret: dict[str, list] = {}
        # TODO: replate str by real type
        ret.setdefault(str(TestState.SUCCESS), [])
        ret.setdefault(str(TestState.FAILURE), [])
        ret.setdefault(str(TestState.SOFT_TIMEOUT), [])
        ret.setdefault(str(TestState.HARD_TIMEOUT), [])
        ret.setdefault(str(TestState.ERR_DEP), [])
        ret.setdefault(str(TestState.ERR_OTHER), [])
        return ret

    def discover_result_files(self) -> None:
        """
        Load existing results from prefix.
        """
        jobs: list[str] = []
        for f in os.listdir(self._outdir):
            if f.startswith("jobs-") and f.endswith(".json"):
                jobs.append(f)

        if len(jobs) > 0:
            curfile = None
            for f in list(map(lambda x: os.path.join(self._outdir, x), jobs)):
                p = os.path.dirname(f)
                f = os.path.splitext(os.path.basename(f))[0]
                curfile = ResultFile(p, f)
                curfile.load()
                self._opened_files[f] = curfile

            self._current_file = curfile

    def build_bidir_map_data(self) -> None:
        """
        Rebuild global views from partial storage on disk.

        For optimization reasons, information that may be rebuilt are not stored
        on disk to save space.
        """
        if not self._mapdata:
            return

        for fic, jobs in self._mapdata.items():
            for job in jobs:
                self._mapdata_rev[job] = fic

    def reconstruct_map_data(self) -> None:
        for job in self.browse_tests():
            self._mapdata_rev[job.jid] = job.output_info["file"]
            self._mapdata.setdefault(job.output_info["file"], [])
            self._mapdata[job.output_info["file"]].append(job.jid)

    def reconstruct_view_data(self) -> None:
        for job in self.browse_tests():
            state = str(job.state)
            job_id = job.jid
            self._viewdata["status"][state].append(job_id)
            for tag in job.tags:
                if tag not in self._viewdata["tags"]:
                    self.register_view_item(view="tags", item=tag)
                self._viewdata["tags"][tag][state].append(job_id)

            self.register_view_item("tree", job.label)
            self._viewdata["tree"][job.label][state].append(job_id)
            if job.subtree:
                nodes = job.subtree.split("/")
                nb_nodes = len(nodes)
                for i in range(1, nb_nodes + 1):
                    name = "/".join([job.label] + nodes[:i])
                    self.register_view_item("tree", name)
                    self._viewdata["tree"][name][state].append(job_id)

    def __init__(
        self, prefix: str = ".", per_file_max_ent: int = 0, per_file_max_sz: int = 0
    ) -> None:
        """
        Initialize a new instance to manage results in a build directory.

        :param prefix: result directory, defaults to "."
        :type prefix: str, optional
        :param per_file_max_ent: max number of tests per output file, defaults
            t(o unlimited (0)
        :type per_file_max_ent: int, optional
        :param per_file_max_sz: max size (bytes) for a single file, defaults to unlimited
        :type per_file_max_sz: int, optional
        """
        self._current_file = None
        self._outdir: str = prefix
        self._opened_files: dict[str, ResultFile] = {}

        map_filename = os.path.join(prefix, "maps.json")
        view_filename = os.path.join(prefix, "views.json")

        def preload_if_exist(path: str, default: dict[str, Any]) -> dict[str, Any]:
            """
            Internal function: populate a file if found in dest dir.

            :param path: file to load
            :type path: str
            :param default: default value if file not found
            :type default: Any
            :return: the dict mapping the data
            :rtype: dict
            """
            if os.path.isfile(path):
                with open(path, "r") as fh:
                    try:
                        json_dict = json.load(fh)
                        assert isinstance(json_dict, dict)
                        return json_dict
                    except Exception:
                        return {}
            else:
                return default

        self._mapdata = preload_if_exist(map_filename, {})
        # TODO: split mapdata_rev into 2 dicts
        self._mapdata_rev: dict[str, str | Test] = {}
        self._viewdata = preload_if_exist(
            view_filename,
            {
                "status": self._ret_state_split_dict(),
            },
        )

        self._max_entries = per_file_max_ent
        self._max_size = per_file_max_sz

        self.build_bidir_map_data()

        self.discover_result_files()
        if not self._current_file:
            self.create_new_result_file()

        # the state view's layout is special, create directly from definition
        # now create basic view as well through the proper API
        self.register_view("tags")
        self.register_view_item(view="tags", item="compilation")

        self.register_view("tree")

    def save(self, job: Test) -> None:
        """
        Add a new job to be saved to the result directory.

        May not be flushed right away to disk, some caching may be used to
        improve performance. While adding the Test to low-level manager, this
        function also updates view & maps accordingly.

        :param job: the job element to store
        :type job: class:`Test`
        """
        job_id = job.jid
        if job_id in self._mapdata.keys():
            raise PublisherException.AlreadyExistJobError(job.name)

        # create a new file if the current one is 'large' enough
        assert self._current_file is not None
        if (self._current_file.size >= self._max_size and self._max_size) or (
            self._current_file.count >= self._max_entries and self._max_entries
        ):
            self.create_new_result_file()

        # save info to file
        self._current_file.save(job_id, job.to_json(), job.encoded_output)

        # register this location from the map-id table
        self._mapdata_rev[job_id] = self._current_file.prefix
        assert self._current_file.prefix in self._mapdata
        self._mapdata[self._current_file.prefix].append(job_id)
        # record this save as a FAILURE/SUCCESS statistic for multiple views
        state = str(job.state)
        self._viewdata["status"][state].append(job_id)
        for tag in job.tags:
            if tag not in self._viewdata["tags"]:
                self.register_view_item(view="tags", item=tag)
            self._viewdata["tags"][tag][state].append(job_id)

        self.register_view_item("tree", job.label)
        self._viewdata["tree"][job.label][state].append(job_id)
        if job.subtree:
            nodes = job.subtree.split("/")
            nb_nodes = len(nodes)
            for i in range(1, nb_nodes + 1):
                name = "/".join([job.label] + nodes[:i])
                self.register_view_item("tree", name)
                self._viewdata["tree"][name][state].append(job_id)

    def retrieve_test(self, job_id: str) -> Optional[Test]:
        """
        Build the Test object mapped to the given job id.

        If such ID does not exist, it will return None.

        :param job_id: _description_
        :type job_id: _type_
        :return: _description_
        :rtype: List[Test]
        """
        if job_id not in self._mapdata_rev:
            return None
        assert self._current_file is not None
        filename = self._mapdata_rev[job_id]
        assert isinstance(filename, str)
        handler = None
        if filename == self._current_file.metadata_prefix:
            handler = self._current_file
        elif filename in self._opened_files:
            handler = self._opened_files[filename]
        else:
            handler = ResultFile(self._outdir, filename)
            self._mapdata[filename] = handler

        res = handler.retrieve_test(job_id=job_id)
        if res:
            if len(res) > 1:
                raise CommonException.UnclassifiableError(
                    reason="Given info leads to more than one job",
                    dbg_info={"data": job_id, "matches": str(res)},
                )
            else:
                return res[0]
        else:
            return None

    def browse_tests(self) -> Iterable[Test]:
        """
        Iterate over every job stored into this build directory.

        :return: an iterable of Tests
        :rtype: List of tests
        :yield: Test
        :rtype: Iterator[Test]
        """
        for hdl in self._opened_files.values():
            yield from hdl.content

    def retrieve_tests_by_name(self, name: str) -> list[Test]:
        """
        Locate a test by its name.

        As multiple matches could occur, this function return a list of class:`Test`

        :param name: the test name
        :type name: str
        :return: the actual list of test, empty if no one is found
        :rtype: list
        """
        ret = []
        for hdl in self._opened_files.values():
            ret += hdl.retrieve_test(name=name)
        return ret

    def register_view(self, name: str) -> None:
        """
        Initialize a new view for this result manager.

        :param name: the view name
        :type name: str
        """
        self._viewdata.setdefault(name, {})

    def register_view_item(self, view: str, item: str) -> None:
        """
        Initialize a single item within a view.

        :param view: the view name (created if not exist)
        :type view: str
        :param item: the item
        :type item: str
        """
        if view not in self._viewdata:
            self.register_view(view)

        self._viewdata[view].setdefault(item, self._ret_state_split_dict())

    def create_new_result_file(self) -> None:
        """
        Initialize a new result file handler upon request.
        """
        filename = self.file_format.format(ResultFileManager.increment)
        ResultFileManager.increment += 1
        self._current_file = ResultFile(self._outdir, filename)
        self._opened_files[filename] = self._current_file
        self._mapdata.setdefault(self._current_file.prefix, [])

    def flush(self) -> None:
        """
        Ensure everything is in sync with persistent storage.
        """
        if self._current_file:
            self._current_file.flush()

        with open(os.path.join(self._outdir, "maps.json"), "w") as fh:
            json.dump(self._mapdata, fh)

        with open(os.path.join(self._outdir, "views.json"), "w") as fh:
            json.dump(self._viewdata, fh)

    @property
    def views(self) -> dict:
        """
        Returns available views for the current instance.

        :return: the views
        :rtype: dict
        """
        return self._viewdata

    @property
    def maps(self) -> dict:
        """
        Returns available views from the current instance.

        :return: the maps
        :rtype: dict
        """
        return self._mapdata

    @property
    def total_cnt(self) -> int:
        """
        Returns the total number of jobs from that directory (=run).

        :return: number of jobs
        :rtype: int
        """
        return len(self._mapdata_rev.keys())

    def map_id(self, job_id: str) -> Test | None:
        """
        Comnvert a job ID into its class:`Test` representation.

        :param job_id: job id
        :type job_id: int
        :return: the associated Test object or None if not found
        :rtype: class:`Test` or None
        """
        if job_id not in self._mapdata_rev:
            return None
        res = self._mapdata_rev[job_id]
        # if the mapped object is already resolved:
        if isinstance(res, Test):
            return res

        if res not in self._opened_files:
            self._opened_files[res] = ResultFile(self._outdir, res)
        hdl = self._opened_files[res]

        match = hdl.retrieve_test(job_id=job_id)
        assert len(match) <= 1
        if match:
            # cache the mapping
            self._mapdata_rev[job_id] = match[0]
            return match[0]
        else:
            return None

    @property
    def status_view(self) -> dict:
        """
        Returns the status view provided by PCVS.

        :return: a view
        :rtype: dict
        """
        status = self._viewdata["status"]
        assert isinstance(status, dict)
        return status

    @property
    def tags_view(self) -> dict:
        """
        Get the tags view provided by PCVS.

        :return: a view
        :rtype: dict
        """
        tags = self._viewdata["tags"]
        assert isinstance(tags, dict)
        return tags

    @property
    def tree_view(self) -> dict:
        """
        Get the tree view, provided by default.

        :return: a view
        :rtype: dict
        """
        tree = self._viewdata["tree"]
        assert isinstance(tree, dict)
        return tree

    def subtree_view(self, subtree: str) -> dict | None:
        """
        Get a subset of the 'tree' view. Any LABEL/subtree combination is valid.

        :param subtree: the prefix to look for
        :type subtree: str
        :return: the dict mapping tests to the request
        :rtype: dict
        """
        if subtree not in self._viewdata["tree"]:
            return None
        subtree = self._viewdata["tree"][subtree]
        assert isinstance(subtree, dict)
        return subtree

    def finalize(self) -> None:
        """
        Flush & close the current manager.

        This instance should not be used again after this call.
        """
        self.flush()
        if self._current_file:
            self._current_file.close()

        for f in self._opened_files.values():
            f.close()

    def __repr__(self) -> str:
        return repr(self.__dict__)

    def __rich_repr__(self) -> Iterable[tuple[str, Any]]:
        return self.__dict__.items()


class BuildDirectoryManager:
    """
    This class is intended to serve a build directory from a single entry
    point. Any module requiring to deal with resources from a run should be
    compliant with this interface. It provides basic mechanism to load/save any
    past, present or future executions.
    """

    def __init__(self, build_dir: str = "."):
        """
        Initialize a new instance.

        This is not destructive, it won't delete any existing resource created
        from previous execution. It will mainly flag this directory as a valid
        PCVS build directory.

        :param build_dir: the build dir, defaults to "."
        :type build_dir: str, optional
        """
        if not os.path.isdir(build_dir):
            raise CommonException.NotFoundError(
                reason="Invalid build directory, should exist *before* init.",
                dbg_info={"build prefix": build_dir},
            )

        self._path: str = build_dir
        self._extras: list[str] = []
        self._results: ResultFileManager | None = None
        self._archive_path: str | None = None
        self._config: MetaConfig | None = None
        self._scratch: str = os.path.join(build_dir, pcvs.NAME_BUILD_SCRATCH)
        old_archive_dir: str = os.path.join(build_dir, pcvs.NAME_BUILD_ARCHIVE_DIR)

        open(os.path.join(self._path, pcvs.NAME_BUILDFILE), "w").close()

        if not os.path.isdir(old_archive_dir):
            os.makedirs(old_archive_dir)

    def init_results(self, per_file_max_sz: int = 0) -> None:
        """
        Initialize the result handler.

        This function is not called directly from the __init__ method as this
        instance may be used for both reading & writing into the destination
        directory. This function implies storing a new execution.

        :param per_file_max_sz: max file size, defaults to unlimited
        :type per_file_max_sz: int, optional
        """
        resdir = os.path.join(self._path, pcvs.NAME_BUILD_RESDIR)
        if not os.path.exists(resdir):
            os.makedirs(resdir)

        self._results = ResultFileManager(prefix=resdir, per_file_max_sz=per_file_max_sz)

    @property
    def results(self) -> ResultFileManager:
        """
        Getter to the result handler, for direct access

        :return: the result handler
        :rtype: class:`ResultFileManager`
        """
        assert self._results is not None
        return self._results

    @property
    def prefix(self) -> str:
        """
        Get the build directory prefix

        :return: the build path
        :rtype: str
        """
        return self._archive_path if self._archive_path else self._path

    def prepare(self, reuse: bool = False) -> None:
        """
        Prepare the dir for a new run.

        This function is not included as part of the __init__ function as this
        instance may be used both for reading & writing into the destination
        directory. This function implies all previous results be be cleared off.

        :param reuse: keep previously generated YAML test-files, defaults to False
        :type reuse: bool, optional
        """
        if not reuse:
            self.clean(pcvs.NAME_BUILD_SCRATCH)
        self.clean(pcvs.NAME_BUILD_RESDIR)
        self.clean(pcvs.NAME_BUILD_CONF_FN)
        self.clean(pcvs.NAME_BUILD_CONF_SH)
        self.clean(pcvs.NAME_BUILD_CACHEDIR)
        self.clean(pcvs.NAME_BUILD_CONTEXTDIR)

        self.clean_archives()

        self.save_extras(pcvs.NAME_BUILD_CACHEDIR, directory=True, export=False)
        self.save_extras(pcvs.NAME_BUILD_CONTEXTDIR, directory=True, export=False)
        self.save_extras(pcvs.NAME_BUILD_SCRATCH, directory=True, export=False)

    @property
    def sid(self) -> str:
        """
        Return the run ID as per configured with the current build directory.

        If not found, this function may return None

        :return: the session ID
        :rtype: str
        """
        assert self._config is not None
        assert "sid" in self._config["validation"]
        sid = self._config["validation"]["sid"]
        assert isinstance(sid, str)
        return sid

    @sid.setter
    def sid(self, sid: str) -> None:
        assert self._config is not None
        self._config["validation"]["sid"] = sid

    def load_config(self) -> MetaConfig:
        """
        Load config stored onto disk & populate the current instance.

        :return: the loaded config
        :rtype: class:`MetaConfig`
        """
        with open(os.path.join(self._path, pcvs.NAME_BUILD_CONF_FN), "r") as fh:
            self._config = MetaConfig(YAML(typ="safe").load(fh))

        return self._config

    def use_as_global_config(self) -> None:
        assert self._config is not None
        GlobalConfig.root = self._config

    def save_config(self, config: MetaConfig) -> None:
        """
        Save the config & store it directly into the build directory.

        :param config: config
        :type config: class:`MetaConfig`
        """
        assert isinstance(config, MetaConfig)
        self._config = config
        with open(os.path.join(self._path, pcvs.NAME_BUILD_CONF_FN), "w", encoding="utf-8") as fh:
            h = YAML(typ="safe")
            h.default_flow_style = False
            h.dump(config.to_dict(), fh)

    @property
    def config(self) -> MetaConfig:
        """
        Return the configuration associated with the current build directory

        :return: config struct
        :rtype: class:`MetaConfig`
        """
        assert self._config is not None
        return self._config

    def add_cache_entry(self, idx: int = 0) -> str:
        d = os.path.join(self._path, pcvs.NAME_BUILD_CONTEXTDIR, str(idx))

        if os.path.exists(d):
            raise CommonException.AlreadyExistError(d)
        else:
            os.makedirs(d)

        return d

    def get_cache_entry(self, idx: int = 0) -> str:
        return os.path.join(self._path, pcvs.NAME_BUILD_CONTEXTDIR, str(idx))

    def save_extras(
        self, rel_filename: str, data: str = "", directory: bool = False, export: bool = False
    ) -> None:
        """
        Register a specific build-relative path, to be saved into the directory.

        The only entry-point to save a resource into it. Resources can be files
        (with or without content) or directory.

        If `export` is set to True, resource (file or whole directory) will also
        be copied to the final archive.

        :param rel_filename: the filepath, relative to build dir.
        :type rel_filename: str
        :param data: data to be saved into the target file, defaults to ""
        :type data: Any, optional
        :param directory: is it a directory to save, defaults to False
        :type directory: bool, optional
        :param export: should the target be also exported in final archive, defaults to False
        :type export: bool, optional
        """
        if os.path.isabs(rel_filename):
            raise CommonException.UnclassifiableError(
                reason="Extras should be saved as relative paths",
                dbg_info={"filename": rel_filename},
            )

        if directory:
            try:
                os.makedirs(os.path.join(self._path, rel_filename))
            except FileExistsError:
                io.console.warn("subprefix {} existed before registering".format(rel_filename))
        else:
            d = os.path.dirname(rel_filename)
            if not os.path.isdir(d):
                os.makedirs(d)

            with open(os.path.join(self._path, rel_filename), "w") as fh:
                fh.write(data)

        if export:
            self._extras.append(rel_filename)

    def clean(self, prefix: str) -> None:
        """
        Prepare the build directory for a new execution by removing anything not
        relevant for a new run.

        Please not this function will erase anything not relative to PCVS. As an
        argument, one may specify a specific prefix to be removed. Paths should
        relative to root build directory.
        """
        assert utils.check_is_buildir(self._path)
        if prefix:
            path = os.path.join(self._path, prefix)
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        else:
            for f in os.listdir(self._path):
                current = os.path.join(self._path, f)
                if not utils.check_is_archive(current):
                    shutil.rmtree(current)

    def clean_archives(self) -> None:
        """
        Prepare the build directory for a new execution by moving any previous
        archive to the backup directory named after NAME_BUILD_ARCHIVE_DIR.
        """
        assert utils.check_is_buildir(self._path)
        for f in os.listdir(self._path):
            current = os.path.join(self._path, f)
            if utils.check_is_archive(current):
                shutil.move(current, os.path.join(self._path, pcvs.NAME_BUILD_ARCHIVE_DIR, f))

    def create_archive(self, timestamp: datetime.datetime | None = None) -> str:
        """
        Generate an archive for the build directory.

        This archive will be stored in the root directory..

        :param timestamp: file suffix, defaults to current timestamp
        :type timestamp: Datetime, optional
        :return: the archive path name
        :rtype: str
        """

        # ensure all results are flushed away before creating the archive
        self.results.finalize()

        if not timestamp:
            timestamp = datetime.datetime.now()
        str_timestamp = timestamp.strftime("%Y%m%d%H%M%S")
        archive_file = os.path.join(self._path, "pcvsrun_{}.tar.gz".format(str_timestamp))
        archive = tarfile.open(archive_file, mode="w:gz")

        def __relative_add(path: str, recursive: bool = False) -> None:
            archive.add(
                path,
                arcname=os.path.join(
                    "pcvsrun_{}".format(str_timestamp), os.path.relpath(path, self._path)
                ),
                recursive=recursive,
            )

        # copy results
        __relative_add(os.path.join(self._path, pcvs.NAME_BUILD_RESDIR), recursive=True)
        # copy the config
        __relative_add(os.path.join(self._path, pcvs.NAME_BUILD_CONF_FN))
        __relative_add(os.path.join(self._path, pcvs.NAME_DEBUG_FILE))

        not_found_files = list()
        for p in self._extras:
            if not os.path.exists(p):
                not_found_files.append(p)
            __relative_add(p)

        if len(not_found_files) > 0:
            raise CommonException.NotFoundError(
                reason="Extra files to be stored to archive do not exist",
                dbg_info={"Failed paths": str(not_found_files)},
            )

        archive.close()
        return archive_file

    @classmethod
    def load_from_archive(cls, archive_path: str) -> Self:
        """
        Populate the instance from an archive.

        This object is initially built to load data from a build directory. This
        way, the object is mapped with an existing archive.

        .. warning::
            This method does not support (yet) to save tests after an archive has
            been loaded (as no output directory has been configured).

        :param archive_path: _description_
        :type archive_path: _type_
        :return: _description_
        :rtype: _type_
        """
        archive = tarfile.open(archive_path, mode="r:gz")

        path = tempfile.mkdtemp(prefix="pcvs-archive")
        archive.extractall(path)
        archive.close()

        d = [x for x in os.listdir(path) if x.startswith("pcvsrun_")]
        assert len(d) == 1
        hdl = BuildDirectoryManager(build_dir=os.path.join(path, d[0]))
        hdl.load_config()
        hdl._archive_path = archive_path
        return hdl  # type: ignore

    def finalize(self) -> None:
        """
        Close & release the current instance.

        It should not be used to save tests after this call.
        """
        self.results.finalize()

    @property
    def scratch_location(self) -> str:
        """
        Returns where third-party artifacts must be stored

        :return: the scratch directory
        :rtype: str
        """
        return self._scratch

    def __repr__(self) -> str:
        return repr(self.__dict__)

    def __rich_repr__(self) -> Iterable[tuple[str, Any]]:
        return self.__dict__.items()
