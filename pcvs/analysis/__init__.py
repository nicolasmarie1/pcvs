"""
Analysis Package.

Used to query information for Analysis from a finished pcvs run through the dsl layer.
"""

from abc import ABC
from typing import Any

from typeguard import typechecked

from pcvs.dsl import Bank
from pcvs.dsl import Series
from pcvs.testing.teststate import TestState


@typechecked
class BaseAnalysis(ABC):

    def __init__(self, bank: Bank):
        self._bank = bank


@typechecked
class SimpleAnalysis(BaseAnalysis):

    def generate_series_trend(self, series: Series, limit: int) -> list[dict[str, Any]]:
        """
        Generate series trend.

        :param series: the series to get a trend of.
        :param limit: the number of run to get the trend on.
        :return: run date, and tests status summary for each run
        """
        stats = []
        for run in series.history(limit):
            ci_meta = run.get_info()
            run_meta = run.get_metadata()
            stats.append({"date": ci_meta["date"], **run_meta})

        return stats

    def generate_series_infos(
        self,
        series: Series,
        limit: int,
        # date -> job_name -> (base_name, state, time)
    ) -> dict[str, dict[str, tuple[str, TestState, float]]]:
        """
        Get series information.

        :param series: the series to get information of.
        :param limit: the number of run to look back.
        :return: test base name, test status & test duration for each jobs for each run date.
        """
        stats = {}
        for run in series.history(limit):
            date = run.get_info()["date"]
            run_stat = {}
            for job in run.jobs:
                run_stat[job.name] = (job.basename, job.state, job.time)
            stats[date] = run_stat
        return stats


@typechecked
class ResolverAnalysis(BaseAnalysis):

    def __init__(self, bank: Bank):
        super().__init__(bank)
        self._data: dict[str, Any] | None = None

    def fill(self, data: dict[str, Any]) -> None:
        assert isinstance(data, dict)
        self._data = data
