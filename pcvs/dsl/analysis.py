from abc import ABC

from pcvs.dsl import Serie


class BaseAnalysis(ABC):

    def __init__(self, bank):
        self._bank = bank


class SimpleAnalysis(BaseAnalysis):

    def generate_serie_trend(self, serie, limit: int):
        if not isinstance(serie, Serie):
            serie = self._bank.get_serie(serie)
        stats = []
        for run in serie.history(limit):
            ci_meta = run.get_info()
            run_meta = run.get_metadata()
            stats.append({"date": ci_meta["date"], **run_meta})

        return stats

    def generate_serie_infos(self, serie: Serie, limit: int):
        if not isinstance(serie, Serie):
            serie = self._bank.get_serie(serie)
        stats = {}
        for run in serie.history(limit):
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
