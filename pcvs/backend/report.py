import os
import random
from typing import Dict
from typing import Iterable
from typing import List
from typing import Union

from ruamel.yaml import YAML

import pcvs
from pcvs.backend.session import list_alive_sessions
from pcvs.backend.session import Session
from pcvs.helpers import utils
from pcvs.helpers.exceptions import CommonException
from pcvs.orchestration.publishers import BuildDirectoryManager
from pcvs.webview import create_app
from pcvs.webview import data_manager


def upload_buildir_results(buildir) -> None:
    """Upload a whole test-suite from disk to the server data model.

    :param buildir: the build directory
    :type buildir: str
    """

    # first, need to determine the session ID -> conf.yml
    with open(os.path.join(buildir, "conf.yml"), "r", encoding="utf-8") as fh:
        conf_yml = YAML().load(fh)

    sid = conf_yml["validation"]["sid"]
    dataman = data_manager

    man = BuildDirectoryManager(buildir)
    dataman.insert_session(
        sid,
        {
            "buildpath": buildir,
            "state": Session.State.COMPLETED,
            "dirs": conf_yml["validation"]["dirs"],
        },
    )
    for test in man.results.browse_tests():
        # FIXME: this function does not exist any more
        # man.save(test)
        dataman.insert_test(sid, test)

    dataman.close_session(sid, {"state": Session.State.COMPLETED})


class Report:
    """
    Map a Report interface, to handle request from frontends.
    """

    def __init__(self) -> None:
        """
        Initialize a new report (no args)
        """
        self._sessions = {}
        self._alive_session_infos = {}

    def __create_build_handler(self, path) -> BuildDirectoryManager:
        """
        Initialize a new handler to a build directory.

        This object will be used to forward result requests.

        :param path: build directory path
        :type path: str
        :raises NotPCVSRelated: Invalid path is provided
        :return: the actual handler
        :rtype: BuildDirectoryManager
        """
        if utils.check_is_buildir(path):
            hdl = BuildDirectoryManager(path)
        elif utils.check_is_archive(path):
            hdl = BuildDirectoryManager.load_from_archive(path)
        else:
            raise CommonException.NotPCVSRelated(
                reason="Given path is not PCVS build related", dbg_info={"path": path}
            )
        return hdl

    def add_session(self, path) -> BuildDirectoryManager:
        """
        Insert new session to be managed.

        :param path: the build path (root dir)
        :type path: str
        :return: the session handler
        :rtype: BuildDirectoryManager
        """
        hdl = self.__create_build_handler(path)
        hdl.load_config()
        hdl.init_results()
        self._sessions[hdl.sid] = hdl
        return hdl

    def load_alive_sessions(self) -> None:
        """
        Load currently active sessions as reference in PATH_SESSION.

        A issue with this function,  as invalid sessions are not managet yet.
        """
        self._alive_session_infos = list_alive_sessions()

        for sk, sv in self._alive_session_infos.items():
            hdl = self.__create_build_handler(sv["path"])
            if hdl.sid in self._sessions:
                # SID may be recycled
                # just attribute another number (negative, to make it noticeable)
                while hdl.sid in self._sessions:
                    hdl.sid = random.randint(0, 10000) * (-1)

            elif hdl.sid != sk:
                # The build directory has been reused since this session ended
                # mark the old one as 'unavailable'
                pass

            self.add_session(sv["path"])

    @property
    def session_ids(self) -> List[int]:
        """
        Get the list of session ids managed by this instance.

        :return: a list of session ids
        :rtype: list of integers
        """
        return list(self._sessions.keys())

    def dict_convert_list_to_cnt(self, arrays: Dict[str, List[int]]) -> Dict[str, int]:
        """
        Convert dict of arrays to a dict of array lengths.

        Used to convert dict of per-status jobs to a summary of them.

        :param arrays: the dict of arrays
        :type arrays: dict
        :return: a summary of given dict
        :rtype: dict
        """
        return {k: len(v) for k, v in arrays.items()}

    def session_infos(self) -> Iterable[Dict]:
        """
        Get sesion metadata for each session currently loaded into the instance.
        :rtype: Iterator[Dict[str, Any]]
        """
        for sid, sdata in self._sessions.items():
            counts = self.dict_convert_list_to_cnt(self.single_session_status(sid))
            state = (
                self._alive_session_infos[sid]["state"]
                if sid in self._alive_session_infos
                else Session.State.COMPLETED
            )
            yield {
                "sid": sid,
                "state": str(state),
                "count": counts,
                "path": sdata.prefix,
                "info": sdata.config["validation"].get("message", "No message"),
            }

    def single_session_config(self, sid) -> dict:
        """
        Get the configuration map from a single session.

        :param sid: the sesion ID
        :type sid: int
        :return: the configuration node (=conf.yml)
        :rtype: dict
        """
        assert sid in self._sessions
        d = self._sessions[sid].get_config()
        d["runtime"]["plugin"] = ""
        return d

    def single_session_status(self, sid, status_filter=None) -> Union[Dict, List]:
        """
        Get per-session status infos

        :param sid: Session id to extract info from.
        :type sid: int
        :param filter: optional status to filter in, defaults to None
        :type filter: str, optional
        :return: A dict of statuses (or a single list if the filter is used)
        :rtype: dict or list
        """
        assert sid in self._sessions
        statuses = self._sessions[sid].results.status_view
        if status_filter:
            assert status_filter in statuses
            return statuses[status_filter]
        return statuses

    def single_session_tags(self, sid) -> Dict[str, Dict]:
        """
        Get per-session available tags.

        Outputs a per-status dict.

        :param sid: Session ID
        :type sid: int
        :return: dict of statuses
        :rtype: dict
        """
        assert sid in self._sessions
        return self._sessions[sid].results.tags_view

    def single_session_job_cnt(self, sid) -> int:
        """
        Get per session number of job.

        :param sid: the session ID
        :type sid: int
        :return: The number of jobs (total)
        :rtype: int
        """
        assert sid in self._sessions
        return self._sessions[sid].results.total_cnt

    def single_session_labels(self, sid) -> Dict[str, Dict]:
        """
        Get per-session available labels.

        Outputs a per-status dict.

        :param sid: Session ID
        :type sid: int
        :return: dict of statuses
        :rtype: dict
        """
        assert sid in self._sessions
        labels_info = self._sessions[sid].results.tree_view
        return {
            label: labels_info[label]
            for label in self._sessions[sid].config["validation"]["dirs"].keys()
        }

    def single_session_build_path(self, sid) -> str:
        """
        Get build prefix of a given session.

        :param sid: session ID
        :type sid: int
        :return: build path
        :rtype: str
        """
        assert sid in self._sessions
        return self._sessions[sid].prefix

    def single_session_map_id(self, sid, jid) -> pcvs.testing.test.Test:
        """
        For a given session id, convert a job it into its relative clas:`Test` object.

        :param sid: Session ID
        :type sid: int
        :param jid: Job ID
        :type jid: int
        :return: the Actual test object
        :rtype: Test
        """
        assert sid in self._sessions
        return self._sessions[sid].results.map_id(jid)

    def single_session_get_view(self, sid, name, subset=None, summary=False) -> Dict[str, Dict]:
        """
        Get a specific view from a given session.

        A view consists in a per-status split of jobs depending on the purpose
        of the stored view. PCVS currently provide automatically:
        * Per status
        * Per tags
        * Per labels

        If `subset` is provided, only the nodes matching the key will be
        returned.
        If `summary` is True, a job count will be returned instead of actual
        job ids.

        :param sid: Session ID
        :type sid: int
        :param name: view name
        :type name: str
        :param subset: only a selection of the view, defaults to None
        :type subset: str, optional
        :param summary: Should it be summarized, defaults to False
        :type summary: bool, optional
        :return: the result dict
        :rtype: dict
        """
        if sid not in self._sessions:
            return None

        d = {}
        if name == "tags":
            d = self.single_session_tags(sid)
        elif name == "labels":
            d = self.single_session_labels(sid)
        else:
            return None

        if subset:
            d = {k: v for k, v in d.items() if subset in k}

        if d and summary:
            return {k: self.dict_convert_list_to_cnt(v) for k, v in d.items()}
        return d

    def __repr__(self):
        return repr(self.__dict__)

    def __rich_repr__(self):
        return self.__dict__.items()


def build_static_pages(buildir) -> None:
    """From a given build directory, generate static pages.

    This can be used only for already run test-suites (no real-time support) and
    when Flask cannot/don't want to be used.

    :param buildir: the build directory to load
    :type buildir: str
    :raises WIPError: Not implemented yet
    """
    raise CommonException.WIPError()


def start_server(report: Report):
    """Initialize the Flask server, default to 5000.

    A random port is picked if the default is already in use.
    :param report: The model to be used.
    :type report: Report
    """
    app = create_app(report)
    app.run(host="0.0.0.0", port=int(os.getenv("PCVS_REPORT_PORT", str(5000))), debug=True)
