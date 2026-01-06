#!/usr/bin/env python3

from importlib.metadata import version

# flake8: noqa: E402
# pylint: disable=wrong-import-position
if version("pcvs").find("dirty") != -1:
    from typeguard import install_import_hook

    install_import_hook("pcvs")
    TYPE_CHECKING = True
else:
    TYPE_CHECKING = False

from pcvs import io
from pcvs.cli import cli_bank
from pcvs.cli import cli_config
from pcvs.cli import cli_convert
from pcvs.cli import cli_graph
from pcvs.cli import cli_remote_run
from pcvs.cli import cli_report
from pcvs.cli import cli_run
from pcvs.cli import cli_session
from pcvs.cli import cli_utilities
from pcvs.helpers import storage
from pcvs.helpers import utils
from pcvs.helpers.exceptions import PluginException
from pcvs.plugins import Collection
from pcvs.plugins import Plugin

try:
    import rich_click as click
    from rich import box

    click.rich_click.SHOW_ARGUMENTS = True
    click.rich_click.STYLE_COMMANDS_PANEL_BOX = box.SIMPLE
    click.rich_click.STYLE_OPTIONS_PANEL_BOX = box.SIMPLE
except ImportError:
    import click  # type: ignore

CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help", "-help"],
    "ignore_unknown_options": True,
    "allow_interspersed_args": False,
    "auto_envvar_prefix": "PCVS",
}


def print_version(
    ctx: click.Context, param: click.Parameter, value: bool  # pylint: disable=unused-argument
) -> None:
    """Print current version.

    This is used as an option formatter, PCVS is not event loaded yet.

    :param ctx: Click Context.
    :param param: The click Parameter that is being completed.
    :param value: whether -v was pass and we should print the value.
    """
    if not value or ctx.resilient_parsing:
        return
    pcvs_version = version("pcvs")
    click.echo(f"Parallel Computing Validation System (pcvs) -- version {pcvs_version}")
    ctx.exit()


@click.group(context_settings=CONTEXT_SETTINGS, name="cli")
@click.option(
    "-v",
    "--verbose",
    "verbose",
    show_envvar=True,
    count=True,
    default=0,
    help="Enable PCVS verbosity (cumulative)",
)
@click.option(
    "-d",
    "--debug",
    show_envvar=True,
    default=False,
    help="Enable Debug mode (implies `-vvv`)",
    is_flag=True,
)
@click.option(
    "-c",
    "--color/--no-color",
    "color",
    default=True,
    is_flag=True,
    show_envvar=True,
    help="Use colors to beautify the output",
)
@click.option(
    "-g",
    "--glyph/--no-glyph",
    "encoding",
    default=True,
    is_flag=True,
    show_envvar=True,
    help="enable/disable Unicode glyphs",
)
@click.option(
    "-C",
    "--exec-path",
    "exec_path",
    show_envvar=True,
    default=None,
    type=click.Path(exists=True, file_okay=False),
)
@click.option(
    "-V",
    "--version",
    expose_value=False,
    is_eager=True,
    callback=print_version,
    is_flag=True,
    help="Display current version",
)
@click.option(
    "-P",
    "--plugin-path",
    "plugin_path",
    multiple=True,
    type=click.Path(exists=True),
    show_envvar=True,
    help="Default Plugin PATH",
)
@click.option(
    "-m",
    "--plugin",
    "select_plugins",
    multiple=True,
    help="Default plugin names to enables.",
)
@click.option(
    "-t",
    "--tui",
    is_flag=True,
    default=False,
    show_envvar=True,
    help="Use a TUI-based interface.",
)
@click.pass_context
@io.capture_exception(PluginException.NotFoundError)
@io.capture_exception(PluginException.LoadError)
def cli(
    ctx: click.Context,
    verbose: int,
    color: bool,
    encoding: bool,
    exec_path: str | None,
    plugin_path: tuple[str, ...],
    select_plugins: tuple[str, ...],
    tui: bool,
    debug: bool,
) -> None:
    """PCVS main program."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose if not debug else 10
    ctx.obj["color"] = color
    ctx.obj["encode"] = encoding
    ctx.obj["tui"] = tui

    # Click specific-related
    ctx.color = color

    io.init(color=color, verbose=verbose)
    if TYPE_CHECKING:
        io.console.debug("Type Checking enable.")

    if exec_path is not None:
        storage.set_exec_path(exec_path)

    utils.create_home_dir()

    pcoll = Collection()
    ctx.obj["plugins"] = pcoll

    pcoll.register_default_plugins()

    if plugin_path:
        for path in plugin_path:
            pcoll.register_plugin_by_dir(path)

    for arg in select_plugins:
        for select in arg.split(","):
            pcoll.activate_plugin(select)

    pcoll.invoke_plugins(Plugin.Step.START_BEFORE)

    pcoll.invoke_plugins(Plugin.Step.START_AFTER)


cli.add_command(cli_config.cli_config)
cli.add_command(cli_run.cli_run)
cli.add_command(cli_bank.cli_bank)
cli.add_command(cli_session.cli_session)
cli.add_command(cli_utilities.cli_exec)
cli.add_command(cli_utilities.cli_check)
cli.add_command(cli_utilities.cli_clean)
cli.add_command(cli_utilities.cli_scan)
# cli.add_command(cli_gui.gui)
cli.add_command(cli_report.cli_report)
cli.add_command(cli_remote_run.cli_remote_run)
# cli.add_command(cli_plumbing.resolve)
cli.add_command(cli_convert.cli_convert)
cli.add_command(cli_graph.cli_graph)


# if __name__ == "__main__":
#     cli()
