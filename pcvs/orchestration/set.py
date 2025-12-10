import enum
from typing import Any
from typing import Iterable

from typeguard import typechecked

from pcvs.backend.metaconfig import GlobalConfig
from pcvs.helpers import communications
from pcvs.testing.test import Test


class ExecMode(enum.IntEnum):
    """
    Map the current execution mode of a set.

    - LOCAL: Sets are run by local runners. Runners are threads collocated in
             the same process.
    - ALLOC: Script is provided to user-defined wrapper, intended to prepare
             resource for job scheduling. Runners are processed and the launch
             command is provided as script's arguments. The 'ALLOC' mode
             supposes runners are not actually running on compute resources.
    - REMOTE: Script is provided to user-defined wrapper, intended to prepare
             resource for job scheduling. Runners are processed and the launch
             command is provided as script's arguments. The 'REMOTE' mode
             supposes runners *are* actually running on compute resources
             alongside jobs.
    - BATCH: Script is provided to user-defined wrapper, intended to prepare
             resource for job scheduling. Runners are processed and the launch
             command is provided as script's arguments. The 'BATCH' mode
             supposes the user script to return before completion. An ACK
             method will be required to ensure Runners have properly been
             executed.
    """

    LOCAL = enum.auto()
    ALLOC = enum.auto()
    REMOTE = enum.auto()
    BATCH = enum.auto()


@typechecked
class Set:
    """Gather multiple jobs to be scheduled.

    Created by the manager to manipulate a subset, these jobs are removed from
    the manager during the execution, only reachable from a Set. Sets are
    launched as thread, dealing with their own workflow.

    :ivar _id: unique id
    :type _id: int
    :ivar _size: number of jobs
    :type _size: int
    :ivar _jobs: list of jobs
    :type _jobs: list
    :ivar _completed: True if all jobs have been executed
    :type _completed: bool
    """

    global_increment = 0
    comman: communications.GenericServer | None = None

    def __init__(self, execmode: ExecMode = ExecMode.LOCAL):
        """constructor method."""
        self._id: int = Set.global_increment
        Set.global_increment += 1
        self._size: int = 0
        self._completed: bool = False
        self._execmode: ExecMode = execmode
        self._map: dict[str, Test] = {}
        self.comman: dict[str, Any] | None

        if not self.comman:
            if GlobalConfig.root.get_internal("comman") is not None:
                self.comman = GlobalConfig.root.get_internal("comman")

    @property
    def execmode(self) -> ExecMode:
        """
        Get execution mode for this Set.

        See Set.ExecMode for more information.


        :return: The current exec mode
        :rtype: class:`Set.ExecMode`
        """
        return self._execmode

    @execmode.setter
    def execmode(self, v: ExecMode) -> None:
        """
        Init the exec mode after the Set is created.

        :param v: Desired Execution mode
        :type v: class:`ExecMode`
        """
        self._execmode = v

    def add(self, jobs: Test | list[Test]) -> None:
        """Add a job or a list of jobs to the current Set.

        :param l: a single or a list of jobs
        :type l: :class:`Test` or List[:class:`Test`]
        """
        if not isinstance(jobs, list):
            jobs = [jobs]
        for j in jobs:
            self._map[j.jid] = j
        self._size = len(self._map.keys())

    def find(self, job_hash: str) -> Test | None:
        if job_hash not in self._map:
            return None
        return self._map[job_hash]

    def is_empty(self) -> bool:
        """check is the set is empty (contains no jobs)

        :return: True if there is no jobs
        :rtype: bool
        """
        return self._size <= 0

    @property
    def size(self) -> int:
        """Getter to size property.

        :return: Set size
        :rtype: int
        """
        return self._size

    @property
    def id(self) -> int:
        """Getter to id property.

        :return: Set id
        :rtype: int
        """
        return self._id

    @property
    def dim(self) -> int:
        """Getter to dim property (largest dimension of a single job)

        :return: Set dim
        :rtype: int
        """
        if self._size <= 0:
            return 0
        else:
            return max(map(lambda x: x.get_dim(), self._map.values()))  # type: ignore

    @property
    def content(self) -> Iterable[Test]:
        """Iterable iterating over the job list."""
        for j in self._map.values():
            yield j

    @property
    def completed(self) -> bool:
        """check is the Set is complete and can be flushed down to the manager.

        :return: True if all jobs have been completed.
        :rtype: bool
        """
        return self._completed

    @completed.setter
    def completed(self, b: bool) -> None:
        self._completed = b
