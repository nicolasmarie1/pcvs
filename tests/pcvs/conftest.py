import os
from contextlib import contextmanager
from importlib.metadata import version

from click.testing import CliRunner

from pcvs import PATH_INSTDIR
from pcvs.helpers.storage import ConfigKind
from pcvs.main import cli

if version("click") >= "8.2.0":
    runner = CliRunner()
else:
    runner = CliRunner(mix_stderr=False)  # pylint: disable=unexpected-keyword-arg


def click_call(*cmd):
    return runner.invoke(cli, ["--no-color", "-vvv", *cmd], catch_exceptions=False)


def isolated_fs():
    return runner.isolated_filesystem()


@contextmanager
def dummy_config_fs():
    """Create an isolated fs with default compiler shem as dummy-config.yml."""
    with open(
        os.path.join(PATH_INSTDIR, "templates/config/compiler.default.yml"), "r", encoding="utf-8"
    ) as template:
        yml = template.readlines()
        with isolated_fs() as fs:
            file_path = os.path.join(os.getcwd(), ".pcvs/compiler/dummy-config.yml")
            os.makedirs(os.path.dirname(file_path))
            with open(file_path, "w", encoding="utf-8") as file:
                file.writelines(yml)
            yield fs


@contextmanager
def dummy_profile_fs():
    """Create an isolated fs with defaults configurations."""
    configs = {}
    kinds = [
        ConfigKind.PROFILE,
        ConfigKind.COMPILER,
        ConfigKind.CRITERION,
        ConfigKind.GROUP,
        ConfigKind.MACHINE,
        ConfigKind.RUNTIME,
    ]
    for k in kinds:
        with open(
            os.path.join(
                PATH_INSTDIR, f"templates/config/{str(k)}.default{ConfigKind.get_filetype(k)}"
            ),
            "r",
            encoding="utf-8",
        ) as conft:
            configs[k] = conft.readlines()
    with isolated_fs() as fs:
        for k in kinds:
            file_path = os.path.join(
                os.getcwd(), f".pcvs/{str(k)}/default{ConfigKind.get_filetype(k)}"
            )
            os.makedirs(os.path.dirname(file_path))
            with open(file_path, "w", encoding="utf-8") as file:
                file.writelines(configs[k])
        yield fs
