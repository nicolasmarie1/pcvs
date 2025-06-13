from click.testing import CliRunner
from importlib.metadata import version

from pcvs import main

if version("click") >= "8.2.0":
    runner = CliRunner()
else:
    runner = CliRunner(mix_stderr=False)


def click_call(*cmd):
    return runner.invoke(main.cli, ["--no-color", *cmd], catch_exceptions=False, prog_name="pcvs")


def isolated_fs():
    return runner.isolated_filesystem()
