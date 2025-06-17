import os

from pcvs.orchestration.publishers import BuildDirectoryManager
from pcvs.orchestration.runner import RunnerRemote

try:
    import rich_click as click
    click.rich_click.SHOW_ARGUMENTS = True
except ImportError:
    import click


@click.command(
    "remote-run",
    help="Internal command to re-run a PCVS instance. Should not be used directly")
@click.option("-b",
              "--build",
              "buildir",
              help="target build directory",
              type=click.Path(exists=True))
@click.option("-c",
              "--context-path",
              "ctx_path",
              help="Current Runner Context path",
              type=click.Path(exists=True))
@click.option("-p",
              "--parallel",
              "parallel",
              default=1,
              type=int,
              help="Run jobs concurrently")
@click.pass_context
def remote_run(ctx, buildir, ctx_path, parallel):  # pylint: disable=unused-argument
    """
    This command is not intended to be used by end users. Please reporte any
    failure coming from this invocation.
    """

    if not buildir:
        buildir = os.path.abspath(
            os.path.dirname(os.path.dirname(os.path.dirname(ctx_path))))

    hdl = BuildDirectoryManager(build_dir=buildir)
    hdl.load_config()
    hdl.use_as_global_config()

    runner = RunnerRemote(ctx_path=ctx_path)
    runner.connect_to_context()
    runner.run(parallel=parallel)
