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
    x = []
    total = []
    fail = []
    hard_timeout = []
    soft_timeout = []
    succ = []
    other = []

    for e in status_data:
        nb = sum(e['cnt'].values())
        total.append(nb)

        x.append(e['date'])
        fail.append(e['cnt'].get(str(Test.State.FAILURE), 0))
        hard_timeout.append(e['cnt'].get(str(Test.State.HARD_TIMEOUT), 0))
        soft_timeout.append(e['cnt'].get(str(Test.State.SOFT_TIMEOUT), 0))
        succ.append(e['cnt'].get(str(Test.State.SUCCESS), 0))
        other.append(nb
                     - e['cnt'].get(str(Test.State.SUCCESS), 0)
                     - e['cnt'].get(str(Test.State.FAILURE), 0)
                     - e['cnt'].get(str(Test.State.SOFT_TIMEOUT), 0)
                     - e['cnt'].get(str(Test.State.HARD_TIMEOUT), 0))
    fig, ax = plt.subplots()
    ax.stackplot(x, fail, hard_timeout, soft_timeout, succ, other,
                 labels=["FAILURE", "HARD_TIMEOUT", "SOFT_TIMEOUT", "SUCCESS", "OTHER"],
                 colors=['red', 'orange', 'blue', 'green', "purple"])
    ax.set_title("Sucess Count")
    ax.set_xlabel("Test Date")
    ax.set_ylabel("nb. tests (count)")
    ax.legend(loc="upper left")
    size = fig.get_size_inches()
    if show:
        plt.show()
    if path:
        file_name = serie.name.replace("/", "_")
        fig.set_size_inches(size[0] * 2, size[1] * 2)
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
    time_data = analysis.generate_serie_infos(serie.name, limit)

    unique_jobs_name = []
    unique_jobs_base_name = []
    for run in time_data:
        for job in time_data[run]:
            if job not in unique_jobs_name:
                unique_jobs_name.append(job)
            basename = time_data[run][job]["basename"]
            if basename not in unique_jobs_base_name:
                unique_jobs_base_name.append(basename)

    for job_base_name in unique_jobs_base_name:
        jobs_time_series = {}
        for job_name in unique_jobs_name:
            if job_name.startswith(job_base_name):
                jobs_time_series[job_name] = ([], [])
        for job_name, job_data in jobs_time_series.items():
            for run in time_data:
                if job_name in time_data[run]:
                    job_data[0].append(run)
                    job_data[1].append(time_data[run][job_name]["time"])

        fig, ax = plt.subplots()
        for job_name, job_data in jobs_time_series.items():
            job_spec: str = job_name[len(job_base_name) + 1:]
            if not job_spec:
                job_spec = "default"  # no criterions
            ax.plot(job_data[0], job_data[1], label=job_spec)

        io.console.debug(f"Times for: {job_base_name}")
        ax.set_title(job_base_name)
        ax.set_xlabel("Test Date")
        ax.set_ylabel("Test Duration (s)")
        ax.set_ylim(ymin=0)
        ax.legend(loc="upper left")
        size = fig.get_size_inches()
        if show:
            plt.show()
        if path:
            file_name = job_base_name.replace("/", "_")
            fig.set_size_inches(size[0] * 2, size[1] * 2)
            fig.savefig(os.path.join(path, f"{file_name}.{extension}"))
        plt.close()
