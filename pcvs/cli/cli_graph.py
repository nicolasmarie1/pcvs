import os
import sys

from pcvs import graph
from pcvs import io
from pcvs.backend import bank as pvBank
from pcvs.cli import cli_bank
from pcvs.dsl import analysis

try:
    import rich_click as click

    click.rich_click.SHOW_ARGUMENTS = True
except ImportError:
    import click


@click.command(
    name="graph",
    short_help="Export graph from tests results.",
)
@click.argument(
    "bank_name",
    nargs=1,
    required=True,
    type=str,
    shell_complete=cli_bank.compl_list_banks,
)
@click.option(
    "-t",
    "--types",
    "graph_types",
    required=True,
    type=click.Choice(["rate", "duration", "all"]),
    default=["all"],
    multiple=True,
    help="Type of graphs to show, (sucess rate or test durations).",
)
@click.option(
    "-p",
    "--path",
    "path",
    required=False,
    type=click.Path(
        exists=False,
        file_okay=False,
        dir_okay=True,
        writable=True,
    ),
    help="Folder to save the images. (Exisintg images with the same names will be overidden)",
)
@click.option(
    "-s",
    "--show",
    "show",
    is_flag=True,
    default=False,
    help="Show the images instead/in addition of saving thems. (Default when --path is not specify)",
)
@click.option(
    "-e",
    "--ext",
    "extension",
    required=False,
    default="svg",
    help="Format of image saved when using --path. (See mathplotlib for available options)",
)
@click.option(
    "-l",
    "--limit",
    "limit",
    required=False,
    default=10,
    help="Maximum number of runs to look back in the banks.",
)
@click.pass_context
def cli_graph(
    ctx, bank_name, graph_types, path, show, extension, limit
):  # pylint: disable=unused-argument
    if path is None:
        show = True
    else:
        os.makedirs(path, exist_ok=True)

    if limit < 0:
        limit = sys.maxsize

    bank = pvBank.Bank(token=bank_name)
    serie = bank.get_serie(bank.default_project)
    if not serie:
        raise click.BadArgumentUsage(f"'{bank_name}' project does not exist")
    simple_analysis = analysis.SimpleAnalysis(bank)

    graph_types = set(graph_types)
    if "all" in graph_types:
        graph_types = ["rate", "duration"]

    io.console.debug(f"graph types: {graph_types}")

    if "rate" in graph_types:
        graph.get_status_series(simple_analysis, serie, path, show, extension, limit)

    if "duration" in graph_types:
        graph.get_time_series(simple_analysis, serie, path, show, extension, limit)
