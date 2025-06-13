from click.testing import CliRunner
from importlib.metadata import version

from pcvs.main import cli

if version("click") >= "8.2.0":
    runner = CliRunner()
else:
    runner = CliRunner(mix_stderr=False)


def click_call(*cmd):
    return runner.invoke(cli, ["--no-color", *cmd], catch_exceptions=False)


def isolated_fs():
    return runner.isolated_filesystem()
