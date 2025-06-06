import os
import fcntl
import shutil
import signal
import socket
import subprocess
import time
from contextlib import contextmanager
from shutil import SameFileError

from pcvs import io
from pcvs import NAME_BUILDFILE
from pcvs import NAME_BUILDIR
from pcvs import NAME_SRCDIR
from pcvs import PATH_HOMEDIR
from pcvs import PATH_INSTDIR
from pcvs.helpers.exceptions import CommonException
from pcvs.helpers.exceptions import LockException
from pcvs.helpers.exceptions import RunException

# ###################################
# #    STORAGE SCOPE MANAGEMENT    ##
# ###################################
STORAGES = {
    'global': PATH_INSTDIR,
    'user': PATH_HOMEDIR,
    'local': os.path.realpath(os.path.join(os.getcwd(), NAME_SRCDIR))
}


def create_home_dir():
    """Create a home directory
    """
    if not os.path.exists(PATH_HOMEDIR):
        os.makedirs(PATH_HOMEDIR)


def storage_order():
    """Return scopes in order of searching.

    :return: a list of scopes
    :rtype: list
    """
    return ['local', 'user', 'global']


def check_valid_scope(s):
    """Check if argument is a valid scope (local, user, global).

    :param s: scope to check
    :type s: str
    :raises CommonException.BadTokenError: the argument is not a valid scope
    """
    if s not in storage_order() and s is not None:
        raise CommonException.BadTokenError(s)


def extract_infos_from_token(s, pair="right", single="right", maxsplit=3):
    """Extract fields from tokens (a, b, c) from user's string.

    :param s: the input string
    :type s: str
    :param pair: padding side when only 2 tokens found, defaults to "right"
    :type pair: str, optional
    :param single: padding side when only 1 token found, defaults to "right"
    :type single: str, optional
    :param maxsplit: maximum split number for s, defaults to 3
    :type maxsplit: int, optional
    :return: 3-string-tuple: mapping (scope, kind, name), any of them may be null
    :rtype: tuple
    """

    array = s.split(".")
    if len(array) >= maxsplit:
        return (array[0], array[1], ".".join(array[maxsplit - 1:]))
    elif len(array) == 2:
        # two cases: a.b or b.c
        if pair == 'left':
            return (array[0], array[1], None)
        elif pair == 'span':
            return (array[0], None, array[1])
        else:
            return (None, array[0], array[1])
    elif len(array) == 1:
        if single == "left":  # pragma: no cover
            return (s, None, None)
        elif single == "center":
            return (None, s, None)
        else:
            return (None, None, s)
    else:  # pragma: no cover
        pass
    return (None, None, None)  # pragma: no cover


def __determine_local_prefix(path, prefix):
    """Search for the ``local`` storage in the current (or parent) directory.

    :param path: ``local`` storage
    :type path: os.path, str
    :param prefix: prefix for ``local`` storage
    :type prefix: os.path, str
    :return: complete path to ``local`` storage
    :rtype: os.path, str
    """
    cur = os.path.relpath(path)
    parent = "/"
    while not os.path.isdir(os.path.join(cur, prefix)):
        parent = os.path.dirname(cur)
        # Reach '/' and not found
        if parent == cur:
            cur = path
            break
        # else, look for parent
        cur = parent

    return os.path.relpath(os.path.join(cur, prefix))


def set_local_path(path):
    """Set the prefix for the ``local`` storage.

    :param path: path of the ``local`` storage
    :type path: os.path
    """

    # no update is required, do not touch defaults
    if path is None:
        return

    assert (os.path.isdir(path))
    found = __determine_local_prefix(path, NAME_SRCDIR)

    # if local is the same as user path, discard
    if found in STORAGES.values():
        found = os.path.join(path, NAME_SRCDIR)
    STORAGES['local'] = found


# ###################################
# ###     PATH MANIPULATION      ####
# ###################################


def create_or_clean_path(prefix, dir=False):
    """Create a path or cleans it if it already exists.

    :param prefix: prefix of the path to create
    :type prefix: os.path, str
    :param dir: True if the path is a directory, defaults to False
    :type dir: bool, optional
    """
    if not os.path.exists(prefix):
        if dir:
            os.mkdir(prefix)
        else:
            assert (os.path.isdir(os.path.dirname(prefix)))
            open(prefix, 'w+').close()
        return

    # else, a previous path exists
    if os.path.isdir(prefix):
        shutil.rmtree(prefix)
        os.mkdir(prefix)
    elif os.path.isfile(prefix):
        os.remove(prefix)


@contextmanager
def cwd(path):
    """Change the working directory.

    :param path: new working directory
    :type path: os.path, str
    """
    if not os.path.isdir(path):
        os.mkdir(path)
    oldpwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(oldpwd)


def copy_file(src, dest):
    """Copy a source file into a destination directory.

    :param src: source file to copy.
    :type src: str
    :param dest: destination directory, may not exist yet.
    :type dest: str
    """
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        shutil.copy(src, dest)
    except SameFileError:
        pass


# ###################################
# ###           MISC.            ####
# ###################################


def check_valid_program(p, succ=None, fail=None, raise_if_fail=True):
    """Check if p is a valid program, using the ``which`` function.

    :param p: program to check
    :type p: str
    :param succ: function to call in case of success, defaults to None
    :type succ: optional
    :param fail: function to call in case of failure, defaults to None
    :type fail: optional
    :param raise_if_fail: Raise an exception in case of failure, defaults to True
    :type raise_if_fail: bool, optional
    :raises RunException.ProgramError: p is not a valid program
    :return: True if p is a program, False otherwise
    :rtype: bool
    """
    assert p
    try:
        filepath = shutil.which(p)
        res = os.access(filepath, mode=os.X_OK)
    except TypeError:  # which() can return None
        res = False

    if res is True and succ is not None:
        basename = os.path.basename(p)
        succ(f"'{basename}' found at '{filepath}'")

    if res is False:
        if fail is not None:
            fail(f"'{p}' not found or not an executable")
        if raise_if_fail:
            raise RunException.ProgramError(p)

    return res


def find_buildir_from_prefix(path):
    """Find the build directory from the ``path`` prefix.

    :param path: path to search the build directory from
    :type path: os.path, str
    :raises CommonException.NotFoundError: the build directory is not found
    :return: the path of the build directory
    :rtype: os.path
    """
    # three scenarios:
    # - path = $PREFIX (being a buildir) -> use as build dir
    # - path = $PREFIX (containing a buildir) - > join(.pcvs-build)
    # - otherwise, raise a path error
    if not os.path.isfile(os.path.join(path, NAME_BUILDFILE)):
        path = os.path.join(path, NAME_BUILDIR)
        if not os.path.isfile(os.path.join(path, NAME_BUILDFILE)):
            raise CommonException.NotFoundError("build-dir in {}".format(path))
    return path


def get_lockfile_name(f):
    """From a file to mutex, return the file lock name associated with it.

    For instance for /a/b.yml, the lock file name will be /a/.b.yml.lck

    :param f: the file to mutex
    :type f: str
    """
    path = os.path.dirname(f)
    filename = os.path.basename(f)

    # hide lock file if original file isn't
    if not filename.startswith("."):
        filename = "." + filename

    return os.path.join(path, filename + ".lck")


def unlock_file(f):
    """Remove lock from a directory.

    :param f: file locking the directory
    :type f: os.path
    """
    lf_name = get_lockfile_name(f)
    try:
        if not os.path.isfile(lf_name):
            open(lf_name, "x").close()
    except FileExistsError:
        pass

    try:
        with open(lf_name, "w+") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            if io.console:
                io.console.debug("Unlock {}".format(lf_name))
    except Exception as e:
        if io.console:
            io.console.warning("Issue unlocking {}: {}".format(lf_name, e))
        pass


def lock_file(f, reentrant=False, timeout=None, force=True):
    """Try to lock a directory.

    :param f: name of lock
    :type f: os.path
    :param reentrant: True if this process may have locked this file before,
        defaults to False
    :type reentrant: bool, optional
    :param timeout: time before timeout, defaults to None
    :type timeout: int (seconds), optional
    :raises LockException.TimeoutError: timeout is reached before the directory
        is locked
    :return: True if the file is reached, False otherwise
    :rtype: bool
    """
    if io.console:
        io.console.debug("Attempt locking {}".format(f))
    if force:
        unlock_file(f)
    locked = trylock_file(f, reentrant)
    count = 0
    while not locked:
        time.sleep(1)
        count += 1
        if timeout and count > timeout:
            raise LockException.TimeoutError(f)
        locked = trylock_file(f, reentrant)
    return locked


def trylock_file(f, reentrant=False):
    """Try to lock a file (used in lock_file).

    :param f: name of lock
    :type f: os.path
    :param reentrant: True if this process may have locked this file before,
        defaults to False
    :type reentrant: bool, optional
    :return: True if the file is reached, False otherwise
    :rtype: bool
    """
    lockfile_name = get_lockfile_name(f)

    # touch the file if not exist, not care about FileExists.
    try:
        if not os.path.isfile(lockfile_name):
            open(lockfile_name, "x").close()
    except FileExistsError:
        pass

    try:
        # attempt to acquire the lock
        with open(lockfile_name, "w") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # from here, lock is taken
            fh.write("{}||{}||{}".format(socket.gethostname(), os.getpid(),
                                         42))
            if io.console:
                io.console.debug("Trylock {}".format(lockfile_name))
            return True
    except OSError:
        try:
            hostname, pid = get_lock_owner(f)
            if pid == os.getpid() and hostname == socket.gethostname(
            ) and reentrant:
                io.console.debug(
                    "Already locked {} for this process".format(lockfile_name))
                return True
            if io.console:
                io.console.debug("Not locked, owned by {}:{}".format(
                    hostname, pid))

        except Exception:
            pass  # return False

        return False


def is_locked(f):
    """Is the given file locked somewhere else ?

    :param f: the file to test
    :type f: str
    :return: a boolean indicating wether the lock is hold or not.
    :rtype: bool
    """
    lf_name = get_lockfile_name(f)
    try:
        with open(lf_name, "r") as fh:
            data = fh.read()
            if data:
                return True
    except Exception:
        return False


def get_lock_owner(f):
    """The lock file will contain the process ID owning the lock. This function
    returns it.

    :param f: the original file to mutex
    :type f: str
    :return: the process ID
    :rtype: int
    """
    lf_name = get_lockfile_name(f)
    with open(lf_name, 'r') as fh:
        s = fh.read().strip().split('||')
        assert (int(s[2]) == 42)
        return s[0], int(s[1])


def program_timeout(sig, frame):
    """Timeout handler, called when a SIGALRM is received.

    :param sig: signal number
    :type sig: int
    :param frame: the callee (unused)
    :type f:
    :raises CommonException.TimeoutError: timeout is reached
    """
    assert (sig == signal.SIGALRM)
    raise CommonException.TimeoutError("Timeout reached")


def start_autokill(timeout=None):
    """Initialize a new time to automatically stop the
    current process once time is expired.

    :param timeout: value in seconds before the autokill will be raised
    :type timeout: positive integer
    """
    if isinstance(timeout, int):
        io.console.print_item(
            "Setting timeout to {} second(s)".format(timeout))
        signal.signal(signal.SIGALRM, program_timeout)

        signal.alarm(timeout)


class Program:
    """Simple class to encapsulate process management.

    This is better and should be preferred as importing subprocess everywhere.
    """

    def __init__(self, cmd=None):
        self._cmd = cmd
        self._out = None
        self._rc = None
        self._except = None

    def run(self, input="", shell=False, timeout=0):
        """Run the given program and capture I/Os

        :param input: raw data to be used as stdin
        :type input: str
        :param shell: is the provided command to be run within a shell
        :type shell: boolean
        :param timeout: allowed time before automatically killing the process
        :type timeout: positive integer
        :return: zero if the process started successfully, non-zero
            otherwise.
        :rtype: integer
        """
        try:
            s = subprocess.Popen(self._cmd,
                                 shell=shell,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            self._out = s.communicate(input=input)
            self._rc = s.returncode
        except Exception as e:
            self._except = e
            return 1
        return 0

    @property
    def out(self):
        """Getter to actual execution output.

        :return: stderr/stdout combined
        :rtype: str
        """
        return self._out

    @property
    def rc(self):
        """Getter, effective return code.

        :return: return code
        :rtype: integer
        """
        return self._rc

    @property
    def exception(self):
        """Getter, raised exception (for any reason)

        :return: an Exception-derived object
        :rtype: Exception
        """
        return self._except


def str_dict_as_envvar(d):
    """Convert a dict to a list of shell-compliant variable strings.

    The final result is a regular multiline str, each line being an entry.

    :param d: the dict containing env vars to serialize
    :type d: dict
    :return: the str, containing mulitple lines, each of them being a var.
    :rtype: str
    """
    return "\n".join(["{}='{}'".format(i, d[i]) for i in sorted(d.keys())])


def check_is_buildir(p):
    if not os.path.isdir(p):
        return False
    return NAME_BUILDFILE in os.listdir(p)


def check_is_archive(f):
    if not os.path.isfile(f):
        return False
    return os.path.basename(f).startswith("pcvsrun_")


def check_is_build_or_archive(x):
    return check_is_buildir(x) or check_is_archive(x)


def list_valid_buildirs_in_dir(p):
    return [
        os.path.join(root, d) for root, d, _ in os.walk(p)
        if check_is_buildir(p)
    ]


def list_valid_archive_in_dir(p):
    return [
        os.path.join(root, f) for root, _, f in os.walk(p)
        if check_is_archive(f)
    ]
