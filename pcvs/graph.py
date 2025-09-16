"""
Graph module.

Use dsl.analysis to query data from bank and use theme to create
mathplotlib graphs.
Used by cli.cli_graph to draw graph from the command line.

We create 2 types of graphs:
    - a stacked graph representing the sucess rate over time of a serie of run
    where all the test state are represented as a layer.
    - a graph for each basetest (test without criterions) in witch we
    represent the test duration evolution per run for each criterions
    combinaison.
"""

import os

from matplotlib import pyplot as plt

from pcvs import io
from pcvs.dsl import Serie
from pcvs.dsl.analysis import SimpleAnalysis
from pcvs.testing.test import Test


def get_status_series(analysis: SimpleAnalysis, serie: Serie, path: str, show: bool,
                      extension: str, limit: int):
    """
    get_status_series: create a test state graph.

    :param analysis: the analysis object that will be used to query the bank.
    :param serie: the serie of test used.
    :param path: the path to save the enerated graphs.
    :param show: do we try to show the graphs to the user directly, (need PyQt5).
    :param extension: format/file extension to use when saving the graphs.
    :param limit: nb max of run in the serie to query (use sys.maxsize for not
        limit).
    """
    status_data = analysis.generate_serie_trend(serie.name, limit)
    xlabels = []
    total, fails, htos, stos, succs, other = [], [], [], [], [], []

    for e in sorted(status_data, key=lambda item: item['date']):
        nb = sum(e['cnt'].values())
        fail = e['cnt'].get(str(Test.State.FAILURE), 0)
        hto = e['cnt'].get(str(Test.State.HARD_TIMEOUT), 0)
        sto = e['cnt'].get(str(Test.State.SOFT_TIMEOUT), 0)
        succ = e['cnt'].get(str(Test.State.SUCCESS), 0)

        xlabels.append(e['date'])
        total.append(nb)
        fails.append(fail)
        htos.append(hto)
        stos.append(sto)
        succs.append(succ)
        other.append(nb - (fail + hto + sto + succ))

    fig, ax = plt.subplots()
    ax.stackplot(range(len(status_data)), fails, htos, stos, succs, other,
                 labels=[Test.State.FAILURE.name, Test.State.HARD_TIMEOUT.name,
                         Test.State.SOFT_TIMEOUT.name, Test.State.SUCCESS.name,
                         Test.State.ERR_OTHER.name],
                 colors=['red', 'orange', 'blue', 'green', "purple"])
    ax.xaxis.set_ticks(range(len(status_data)))
    ax.xaxis.set_ticklabels(sorted(xlabels))
    ax.set_title("Sucess Count")
    ax.set_xlabel("Test Date")
    ax.set_ylabel("nb. tests (count)")
    ax.set_ylim(ymin=0)
    ax.legend(loc="upper left")
    size = fig.get_size_inches()
    if show:
        plt.show()
    if path:
        file_name = serie.name.replace("/", "_")
        fig.set_size_inches(size[0] * 2 * max(1, len(status_data) / 6), size[1] * 2)
        fig.savefig(os.path.join(path, f"{file_name}.{extension}"))
    plt.close()


def _get_time_serie(jobs_base_name: str, jobs: dict[str, dict[str, list[int]]],
                    dates: list[int], path: str, show: bool, extension: bool):
    io.console.debug(f"Times for: {jobs_base_name}")
    fig, ax = plt.subplots()
    for job_name, job_data in jobs.items():
        job_spec: str = job_name[len(jobs_base_name) + 1:]
        if not job_spec:
            job_spec = "default"  # no criterions
        ax.plot(job_data["indexs"], job_data["times"], label=job_spec, marker="+")
    ax.xaxis.set_ticks(range(len(dates)))
    ax.xaxis.set_ticklabels(dates)

    ax.set_title(jobs_base_name)
    ax.set_xlabel("Test Date")
    ax.set_ylabel("Test Duration (s)")
    ax.set_ylim(ymin=0)
    ax.legend(loc="upper left")
    size = fig.get_size_inches()
    if show:
        plt.show()
    if path:
        file_name = jobs_base_name.replace("/", "_")
        fig.set_size_inches(size[0] * 2 * max(1, len(dates) / 6), size[1] * 2)
        fig.savefig(os.path.join(path, f"{file_name}.{extension}"))
    plt.close()


def get_time_series(analysis: SimpleAnalysis, serie: Serie, path: str, show: bool,
                    extension: str, limit: int):
    """
    get_time_series: create a test state graph.

    :param analysis: the analysis object that will be used to query the bank.
    :param serie: the serie of test used.
    :param path: the path to save the enerated graphs.
    :param show: do we try to show the graphs to the user directly, (need PyQt5).
    :param extension: format/file extension to use when saving the graphs.
    :param limit: nb max of run in the serie to query (use sys.maxsize for not
        limit).
    """
    all_time_data: dict[int, dict[str, dict[str, str | int]]] = analysis.generate_serie_infos(serie.name, limit)
    group_jobs: dict[str, dict[str, dict[str, list[int]]]] = {}
    group_dates: dict[str, list[int]] = {}

    # -> move struct from: date { job { data } }
    #                  to: jobgroup { job ([index], [data.time]) } } }
    #                   +: jobgroup { [dates] }
    #   ie: group by job basename + swap job/date key order
    # + filter data by state == sucess || state == soft_timeout
    # + make sur we are going by date order to get the right graph.
    i: int = 0
    for run_date, jobs in dict(sorted(all_time_data.items())).items():
        for job_name, job_data in jobs.items():
            base_name = job_data["basename"]
            if base_name not in group_jobs:
                group_jobs[base_name] = {}
                group_dates[base_name] = []
            if run_date not in group_dates[base_name]:
                group_dates[base_name].append(run_date)
            if job_name not in group_jobs[base_name]:
                group_jobs[base_name][job_name] = {"indexs": [],
                                                   "times": []}
            group_jobs[base_name][job_name]["indexs"].append(i)
            if (job_data["status"] == Test.State.SUCCESS or
                    job_data["status"] == Test.State.SOFT_TIMEOUT):
                group_jobs[base_name][job_name]["times"].append(job_data["time"])
            else:
                group_jobs[base_name][job_name]["times"].append(None)
        i += 1

    for jobs_base_name, jobs_data in group_jobs.items():
        dates = group_dates[jobs_base_name]
        _get_time_serie(jobs_base_name, jobs_data, dates, path, show, extension)
