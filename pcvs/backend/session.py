import hashlib
import os
from datetime import datetime
from enum import IntEnum
from multiprocessing import Process
from typing import Any
from typing import Callable

from ruamel.yaml import YAML
from ruamel.yaml.constructor import Constructor
from ruamel.yaml.main import yaml_object
from ruamel.yaml.representer import Representer
from typeguard import typechecked
from typing_extensions import Self

from pcvs import io
from pcvs import PATH_SESSION

yml = YAML()


@typechecked
def session_file_hash(session_infos: dict) -> str:
    return hashlib.sha1(
        "{}:{}".format(session_infos["path"], session_infos["started"]).encode()
    ).hexdigest()


@typechecked
def store_session_to_file(infos: dict) -> str:
    """Save a new session into the session file (in HOME dir).

    :param c: session infos to store
    :type c: dict
    :return: the sid associated to new create session id.
    :rtype: int
    """
    global yml

    if not os.path.exists(PATH_SESSION):
        os.makedirs(PATH_SESSION)

    shash = session_file_hash(infos)
    session_file = os.path.join(PATH_SESSION, "{}.yml".format(shash))
    try:
        with open(session_file, "x") as fh:
            yml.dump(infos, fh)
    except Exception as e:
        raise e
    return shash


@typechecked
def update_session_from_file(sid: str, update: dict) -> bool:
    """Update data from a running session from the global file.

    This only add/replace keys present in argument dict. Other keys remain.

    :param sid: the session id
    :param update: the keys to update. If already existing, content is replaced
    :return: if a session file was successfully modify (== if the session exist)
    """
    global yml

    if not os.path.exists(PATH_SESSION):
        os.makedirs(PATH_SESSION)

    for f in os.listdir(PATH_SESSION):
        if f.startswith(str(sid)):
            with open(os.path.join(PATH_SESSION, f), "r") as fh:
                data = yml.load(fh)

            for k, v in update.items():
                data[k] = v

            with open(os.path.join(PATH_SESSION, f), "w") as fh:
                yml.dump(data, fh)

            return True

    return False


@typechecked
def remove_session_from_file(sid: str) -> bool:
    """clear a session from logs.

    :param sid: the session id to remove.
    :return: if the session was successfully removed. (== if the session exist)
    """
    global yml

    for f in os.listdir(PATH_SESSION):
        if f.startswith(str(sid)):
            os.remove(os.path.join(PATH_SESSION, f))
            return True
    return False


@typechecked
def list_alive_sessions() -> dict[str, dict]:
    """Load and return the complete dict from session.yml file

    :return: the session dict
    :rtype: dict
    """
    global yml
    if not os.path.exists(PATH_SESSION):
        os.makedirs(PATH_SESSION)

    all_sessions = {}

    for f in os.listdir(PATH_SESSION):
        assert os.path.splitext(f) not in all_sessions
        try:
            with open(os.path.join(PATH_SESSION, f), "r") as fh:
                data = yml.load(fh)
                all_sessions[os.path.splitext(f)[0]] = data
        except Exception:
            continue
    return all_sessions


@typechecked
def main_detached_session(sid: str, user_func: Callable, *args, **kwargs) -> int:  # type: ignore
    """Main function processed when running in detached mode.

    This function is called by Session.run_detached() and is launched from
    cloned process (same global env, new main function).

    :raises Exception: Any error occurring during the main process is re-raised.

    :param sid: the session id
    :param user_func: the Python function used as the new main()
    :param args: user_func() arguments
    :type args: tuple
    :param kwargs: user_func() arguments
    :type kwargs: dict
    """

    # When calling a subprocess, the parent is attached to its child
    # Parent won't terminate if a single child is still running.
    # Setting a child 'daemon' will allow parent to terminate children at exit
    # (still not what we want)
    # the trick is to double fork: the parent creates a child, also crating a
    # a child (child2). When the process is run, the first child completes
    # immediately, releasing the parent.
    if os.fork() != 0:
        return 0

    ret = 0

    try:
        # run the code in detached mode
        # beware: this function should only raises exception to stop.
        # a sys.exit() will bypass the rest here.
        ret = user_func(*args, **kwargs)
        assert isinstance(ret, int)
        update_session_from_file(sid, {"state": SessionState.COMPLETED, "ended": datetime.now()})
    except Exception as e:
        update_session_from_file(sid, {"state": SessionState.ERROR, "ended": datetime.now()})
        raise e

    return ret


@typechecked
@yaml_object(yml)
class SessionState(IntEnum):
    """Enum of possible Session states."""

    WAITING = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    ERROR = 3

    @classmethod
    def to_yaml(cls, representer: Representer, data: Self) -> Any:
        """Convert a Test.State to a valid YAML representation.

        A new tag is created: 'Session.State' as a scalar (str).
        :param representer: the YAML dumper object
        :param data: the object to represent
        :return: the YAML representation
        """
        return representer.represent_scalar("!State", "{}||{}".format(data.name, data.value))

    @classmethod
    def from_yaml(cls, constructor: Constructor, node: Any) -> Self:
        """Construct a :class:`Session.State` from its YAML representation.

        Relies on the fact the node contains a 'Session.State' tag.
        :param constructor: the YAML loader
        :param node: the YAML representation
        :return: The session State as an object
        """
        s = constructor.construct_scalar(node)
        name, value = s.split("||")
        obj = SessionState(int(value))
        assert obj.name == name

        return obj  # type: ignore

    def __str__(self) -> str:
        """Stringify the state.

        :return: the enum name.
        :rtype: str
        """
        return self.name


@typechecked
class Session:
    """Object representing a running validation (detached or not).

    Despite the fact it is designed for manage concurrent runs,  it takes a
    callback and can be derived for other needs.

    :param _func: user function to be called once the session starts
    :type _func: Callable
    :param _sid: session id, automatically generated
    :type _sid: str
    :param _session_infos: session infos dict
    :type _session_infos: dict

    """

    @property
    def state(self) -> SessionState:
        """Getter to session status.

        :return: session status
        :rtype: int
        """
        state = self._session_infos["state"]
        assert isinstance(state, SessionState)
        return state

    @property
    def id(self) -> str:
        """Getter to session id.

        :return: session hash
        :rtype: str
        """
        return self._sid

    @property
    def rc(self) -> int:
        """Gett to final RC.

        :return: rc
        """
        return self._rc

    @property
    def infos(self) -> dict[str, Any]:
        """Getter to session infos.

        :return: session infos
        :rtype: dict
        """
        return self._session_infos

    def property(self, kw: str) -> Any:
        """Access specific data from the session stored info session.yml.

        :param kw: the information to retrieve. kw must be a valid key
        :type kw: str
        :return: the requested session infos if exist
        :rtype: Any
        """
        assert kw in self._session_infos
        return self._session_infos[kw]

    def __init__(self, date: datetime | None = None, path: str = "."):
        """constructor method.

        :param date: the start timestamp
        :type date: datetime.datetime
        :param path: the build directory
        :type path: str
        """
        self._func: Callable[..., int] | None = None
        self._rc = -1
        self._sid = str(-1)
        # this dict is then flushed to the session.yml
        self._session_infos = {
            "path": path,
            "log": io.console.logfile,
            "io": io.console.outfile,
            "progress": 0,
            "state": SessionState.WAITING,
            "started": date,
            "ended": None,
        }

    def load_from(self, sid: str, data: dict[str, Any]) -> None:
        """Update the current object with session infos read from global file.

        :param sid: session id read from file
        :type sid: str
        :param data: session infos read from file
        :type data: dict
        """
        self._sid = sid
        self._session_infos = data

    def register_callback(self, callback: Callable[..., int]) -> None:
        """Register the callback used as main function once the session is
        started.

        :param callback: function to invoke
        :type callback: Callable
        """
        self._func = callback

    def run_detached(self, *args, **kwargs) -> str:  # type: ignore
        """Run the session is detached mode.

        Arguments are for user function only.
        :param args: user function positional arguments
        :type args: tuple
        :param kwargs user function keyword-based arguments.
        :type kwargs: tuple

        :return: the Session id created for this run.
        :rtype: str
        """
        io.detach_console()
        self._session_infos["io"] = io.console.outfile

        assert self._func is not None

        # some sessions can have their starting time set directly when
        # initializing the object.
        # for instance for runs, elapsed time not session time but wall time"""
        if self.property("started") is None:
            self._session_infos["started"] = datetime.now()

        # flag it as running & make the info public
        self._session_infos["state"] = SessionState.IN_PROGRESS
        self._sid = store_session_to_file(self._session_infos)

        # run the new process
        child = Process(
            target=main_detached_session, args=(self._sid, self._func, *args), kwargs=kwargs
        )

        child.start()

        return self._sid

    def run(self, *args, **kwargs) -> str:  # type: ignore
        """
        Run the session normally, without detaching the focus.

        Arguments are user function ones. This function is also in charge of
        redirecting I/O properly (stdout, file, logs)

        :param args: user function positional arguments
        :type args: tuple
        :param kwargs: user function keyword-based arguments.
        :type kwargs: tuple
        :return: the session ID for this run
        :rtype: str
        """
        if self._func is not None:
            # same as above, shifted starting time or not
            if self.property("started") is None:
                self._session_infos["started"] = datetime.now()

            self._session_infos["state"] = SessionState.IN_PROGRESS
            self._sid = store_session_to_file(self._session_infos)

            # run the code
            try:
                self._rc = self._func(*args, **kwargs)
            finally:
                # in that mode, no information is left to users once the session
                # is complete.
                remove_session_from_file(self._sid)

        return self._sid
