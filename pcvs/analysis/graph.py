"""
Graph module.

Use dsl.analysis to query data from bank and use theme to create
mathplotlib graphs.
Used by cli.cli_graph to draw graph from the command line.

We create 2 types of graphs:

    - a stacked graph representing the success rate over time of a series of run
      where all the test state are represented as a layer.
    - a graph for each basetest (test without criterions) in witch we
      represent the test duration evolution per run for each criterions
      combination.
"""

import os

from matplotlib import pyplot as plt
from typeguard import typechecked

from pcvs import io
from pcvs.analysis import SimpleAnalysis
from pcvs.dsl import Series
from pcvs.testing.teststate import TestState


@typechecked
def get_status_series(
    analysis: SimpleAnalysis, series: Series, path: str, show: bool, extension: str, limit: int
) -> None:
    """
    get_status_series: create a test state graph.

    :param analysis: the analysis object that will be used to query the bank.
    :param series: the series of test used.
    :param path: the path to save the enerated graphs.
    :param show: do we try to show the graphs to the user directly, (need PyQt5).
    :param extension: format/file extension to use when saving the graphs.
    :param limit: nb max of run in the series to query (use sys.maxsize for not
        limit).
    """
    status_data = analysis.generate_series_trend(series, limit)
    xlabels = []
    total, fails, htos, stos, succs, other = [], [], [], [], [], []

    for e in sorted(status_data, key=lambda item: item["date"]):
        nb = sum(e["cnt"].values())
        fail = e["cnt"].get(str(TestState.FAILURE), 0)
        hto = e["cnt"].get(str(TestState.HARD_TIMEOUT), 0)
        sto = e["cnt"].get(str(TestState.SOFT_TIMEOUT), 0)
        succ = e["cnt"].get(str(TestState.SUCCESS), 0)

        xlabels.append(e["date"])
        total.append(nb)
        fails.append(fail)
        htos.append(hto)
        stos.append(sto)
        succs.append(succ)
        other.append(nb - (fail + hto + sto + succ))

    fig, ax = plt.subplots()
    ax.stackplot(
        range(len(status_data)),
        fails,
        htos,
        stos,
        succs,
        other,
        labels=[
            TestState.FAILURE.name,
            TestState.HARD_TIMEOUT.name,
            TestState.SOFT_TIMEOUT.name,
            TestState.SUCCESS.name,
            TestState.ERR_OTHER.name,
        ],
        colors=["red", "orange", "blue", "green", "purple"],
    )
    ax.xaxis.set_ticks(range(len(status_data)))
    ax.xaxis.set_ticklabels(sorted(xlabels))
    ax.set_title("Success Count")
    ax.set_xlabel("Test Date")
    ax.set_ylabel("nb. tests (count)")
    ax.set_ylim(ymin=0)
    ax.legend(loc="upper left")
    size = fig.get_size_inches()
    if show:
        plt.show()
    if path:
        file_name = series.name.replace("/", "_")
        fig.set_size_inches(size[0] * 2 * max(1, len(status_data) / 6), size[1] * 2)
        fig.savefig(os.path.join(path, f"{file_name}.{extension}"))
    plt.close()


@typechecked
def _get_time_series(
    jobs_base_name: str,
    # testname -> ([rundate -> index], [rundate -> duration])
    jobs: dict[str, tuple[list[int], list[float | None]]],
    dates: list[str],
    path: str,
    show: bool,
    extension: str,
) -> None:
    io.console.debug(f"Times for: {jobs_base_name}")
    fig, ax = plt.subplots()
    for job_name, job_data in jobs.items():
        job_spec: str = job_name[len(jobs_base_name) + 1 :]
        if not job_spec:
            job_spec = "default"  # no criterions
        ax.plot(job_data["indexes"], job_data["times"], label=job_spec, marker="+")  # type: ignore
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


@typechecked
def get_time_series(
    analysis: SimpleAnalysis, series: Series, path: str, show: bool, extension: str, limit: int
) -> None:
    """
    get_time_series: create a test state graph.

    :param analysis: the analysis object that will be used to query the bank.
    :param series: the series of test used.
    :param path: the path to save the enerated graphs.
    :param show: do we try to show the graphs to the user directly, (need PyQt5).
    :param extension: format/file extension to use when saving the graphs.
    :param limit: nb max of run in the series to query (use sys.maxsize for not
        limit).
    """
    # rundate -> jobname -> (basename, teststatus, testduration)
    all_time_data: dict[str, dict[str, tuple[str, TestState, float]]] = (
        analysis.generate_series_infos(series, limit)
    )
    # basename -> name -> ([rundate -> index], [rundate -> duration])
    group_jobs: dict[str, dict[str, tuple[list[int], list[float | None]]]] = {}
    # base_name -> [rundate]
    group_dates: dict[str, list[str]] = {}

    # -> move struct from: date -> job_nape -> (basename, state, time)
    #                  to: jobgroup -> job -> (index, time)
    #                   +: jobgroup -> time
    #   ie: group by job basename + swap job/date key order
    # + filter data by state == success || state == soft_timeout
    # + make sure we are going by date order to get the right graph.
    i: int = 0
    for run_date, jobs in dict(sorted(all_time_data.items())).items():
        for job_name, job_data in jobs.items():
            base_name = job_data[0]
            if base_name not in group_jobs:
                group_jobs[base_name] = {}
                group_dates[base_name] = []
            if run_date not in group_dates[base_name]:
                group_dates[base_name].append(run_date)
            if job_name not in group_jobs[base_name]:
                group_jobs[base_name][job_name] = ([], [])
            group_jobs[base_name][job_name][0].append(i)
            if job_data[1] == TestState.SUCCESS or job_data[1] == TestState.SOFT_TIMEOUT:
                group_jobs[base_name][job_name][1].append(job_data[2])
            else:
                group_jobs[base_name][job_name][1].append(None)
        i += 1

    for jobs_base_name, jobs_data in group_jobs.items():
        dates = group_dates[jobs_base_name]
        _get_time_series(jobs_base_name, jobs_data, dates, path, show, extension)
