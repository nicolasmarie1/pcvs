from abc import ABC

from pcvs.dsl import Series


class BaseAnalysis(ABC):

    def __init__(self, bank):
        self._bank = bank


class SimpleAnalysis(BaseAnalysis):

    def generate_series_trend(self, series, limit: int):
        if not isinstance(series, Series):
            series = self._bank.get_series(series)
        stats = []
        for run in series.history(limit):
            ci_meta = run.get_info()
            run_meta = run.get_metadata()
            stats.append({"date": ci_meta["date"], **run_meta})

        return stats

    def generate_series_infos(self, series: Series, limit: int):
        if not isinstance(series, Series):
            series = self._bank.get_series(series)
        stats = {}
        for run in series.history(limit):
            date = run.get_info()["date"]
            run_stat = {}
            for job in run.jobs:
                run_stat[job.name] = {
                    "basename": job.basename,
                    "status": job.state,
                    "time": job.time,
                }
            stats[date] = run_stat
        return stats


class ResolverAnalysis(BaseAnalysis):

    def __init__(self, bank):
        super().__init__(bank)
        self._data = None

    def fill(self, data):
        assert isinstance(data, dict)
        self._data = data
