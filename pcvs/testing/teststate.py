from enum import IntEnum

from typeguard import typechecked
from typing_extensions import Self


@typechecked
class TestState(IntEnum):
    """Provide Status management, specifically for tests/jobs.

    Defined as an enum, it represents different states a
    :class:`~pcvs.testing.test`/:class:`~pcvs.dsl.Job` can take during
    its lifetime. As tests are then serialized into a JSON file, there is
    no need for construction/representation (as done for
    :class:`~pcvs.backend.session.SessionState`).

    :var int WAITING: Job is currently waiting to be scheduled
    :var int IN_PROGRESS: A running Set() handle the job, and is scheduled
        for run.
    :var int EXECUTED: Job have been executed, but result status
        has not been computed yet.
    :var int SUCCESS: Job successfully run and passes all checks (rc,
        matchers...)
    :var int FAILURE: Job didn't succeed, at least one condition failed.
    :var SOFT_TIMEOUT: Job has exceeded his soft time limit but pass.
    :var HARD_TIMEOUT: Job has exceeded his hard time limit and got killed.
    :var int ERR_DEP: Special cases to manage jobs unscheduled because at
        least one of its dependencies have failed to complete.
    :var int ERR_OTHER: Any other uncaught situation.
    """

    __test__ = False  # prevent pytest from going roge

    WAITING = 0
    IN_PROGRESS = 1
    EXECUTED = 2
    SUCCESS = 3
    FAILURE = 4
    SOFT_TIMEOUT = 5
    HARD_TIMEOUT = 6
    ERR_DEP = 7
    ERR_OTHER = 8

    def __str__(self) -> str:
        """Stringify to return the label.

        :return: the enum name
        :rtype: str
        """
        return self.name

    def __repr__(self) -> str:
        """Enum representation a tuple (name, value).

        :return: a tuple mapping the enum.
        :rtype: tuple
        """
        return f"({self.name}, {self.value})"

    @classmethod
    def from_str(cls, state: str) -> Self | None:
        """Convert str to TestState."""
        str_to_states = {
            TestState.WAITING.name: TestState.WAITING,
            TestState.IN_PROGRESS.name: TestState.IN_PROGRESS,
            TestState.EXECUTED.name: TestState.EXECUTED,
            TestState.SUCCESS.name: TestState.SUCCESS,
            TestState.FAILURE.name: TestState.FAILURE,
            TestState.SOFT_TIMEOUT.name: TestState.SOFT_TIMEOUT,
            TestState.HARD_TIMEOUT.name: TestState.HARD_TIMEOUT,
            TestState.ERR_DEP.name: TestState.ERR_DEP,
            TestState.ERR_OTHER.name: TestState.ERR_OTHER,
        }
        return str_to_states.get(state.upper(), None)  # type: ignore

    @classmethod
    def bad_states(cls) -> list[Self]:
        """State that represent a FAILED test."""
        bad_states = [
            TestState.ERR_DEP,
            TestState.ERR_OTHER,
            TestState.FAILURE,
            TestState.HARD_TIMEOUT,
        ]
        return bad_states  # type: ignore

    @classmethod
    def all_states(cls) -> list[Self]:
        """All tests states."""
        all_states = [
            TestState.SUCCESS,
            TestState.FAILURE,
            TestState.ERR_DEP,
            TestState.HARD_TIMEOUT,
            TestState.SOFT_TIMEOUT,
            TestState.ERR_OTHER,
        ]
        return all_states  # type: ignore
