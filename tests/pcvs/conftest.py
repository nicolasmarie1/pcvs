import os
import shutil
from contextlib import contextmanager
from importlib.metadata import version
from unittest.mock import patch

from click.testing import CliRunner

from pcvs import PATH_INSTDIR
from pcvs.helpers.storage import ConfigKind
from pcvs.helpers.storage import ConfigLocator
from pcvs.helpers.storage import ConfigScope
from pcvs.main import cli

if version("click") >= "8.2.0":
    runner = CliRunner()
else:
    runner = CliRunner(mix_stderr=False)  # pylint: disable=unexpected-keyword-arg


def click_call(*cmd):
    """Run a pcvs command."""
    return runner.invoke(cli, ["--no-color", "-vvv", *cmd], catch_exceptions=False)


@contextmanager
def isolated_fs():
    """Create isolated file system to run test."""
    with runner.isolated_filesystem() as tmp:
        yield tmp


@contextmanager
def dummy_config_fs():
    """Create an isolated fs with default compiler shem as dummy-config.yml."""
    with open(
        os.path.join(PATH_INSTDIR, "config/compiler/default.yml"), "r", encoding="utf-8"
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
    """Create an isolated fs with GLOBAL configurations in LOCAL."""
    with isolated_fs() as tmp_dir:
        for k in ConfigKind.all_kinds():
            ext = ConfigKind.get_file_ext(k)
            src_path = os.path.join(PATH_INSTDIR, f"config/{str(k)}/default{ext}")
            dst_path = os.path.join(tmp_dir, f".pcvs/{str(k)}/default{ext}")
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy(src_path, dst_path)
        yield tmp_dir


@contextmanager
def dummy_fs_profiles_in_tmp():
    """Create a new GLOBAL/USER/LOCAL worktree in /tmp with default configuration copy in each scopes."""
    with dummy_profile_fs() as tmp_dir:
        cwd = os.path.join(tmp_dir, "user", "local")
        glob = os.path.join(tmp_dir, ".pcvs")
        user = os.path.join(tmp_dir, "user", ".pcvs")
        local = os.path.join(tmp_dir, "user", "local", ".pcvs")
        os.makedirs(cwd, exist_ok=True)

        shutil.copytree(glob, user)
        shutil.copytree(glob, local)

        os.chdir(cwd)
        yield (glob, user, local)


@contextmanager
def dummy_fs_with_configlocator_patch():
    """Provide a patched ConfigLocator in /tmp."""
    with dummy_fs_profiles_in_tmp() as (glob, user, local):
        cl = ConfigLocator()
        scopes_to_paths = {
            ConfigScope.GLOBAL: glob,
            ConfigScope.USER: user,
            ConfigScope.LOCAL: local,
        }
        with patch.object(cl, "_storage_scope_paths", new=scopes_to_paths):
            yield (cl, scopes_to_paths)
