import os
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pcvs.helpers import utils as tested
from pcvs.helpers.exceptions import RunException


def test_path_cleaner():
    with CliRunner().isolated_filesystem():
        os.makedirs("./A/B/C/D")
        open("./A/B/C/D/file.txt", "w").close()

        tested.create_or_clean_path("A/B/C/D/file.txt")
        assert not os.path.exists("A/B/C/D/file.txt")
        tested.create_or_clean_path("A/B")
        assert os.path.isdir("A/B")
        assert len(os.listdir("A/B")) == 0


@pytest.mark.parametrize("wd_dir", ["/home", "/", "/tmp", "./dummy-dir"])
def test_cwd_manager(wd_dir):

    with CliRunner().isolated_filesystem():
        ref_path = os.path.abspath(wd_dir)
        with tested.cwd(wd_dir):
            assert os.getcwd() == ref_path


@patch(
    "pcvs.backend.metaconfig.GlobalConfig.root",
    {
        "validation": {
            "output": "/prefix_build",
            "dirs": {
                "LABEL1": "/prefix1",
                "LABEL2": "/prefix2",
            },
        }
    },
)
@pytest.mark.parametrize("program", ["ls", "/bin/sh"])
def test_check_program(program):
    class Success(Exception):
        pass

    def succ_func(msg):
        assert "'{}' found at '".format(os.path.basename(program)) in msg
        raise Success()

    with pytest.raises(Success):
        tested.check_valid_program(program, succ=succ_func)
    tested.check_valid_program(program)


@pytest.mark.parametrize("program", ["invalid-program", "./setup.py"])
def test_check_wrong_program(program):
    class Failure(Exception):
        pass

    def fail_func(msg):
        assert msg == "'{}' not found or not an executable".format(program)
        raise Failure()

    with pytest.raises(Failure):
        tested.check_valid_program(program, fail=fail_func)
    with pytest.raises(RunException.ProgramError):
        tested.check_valid_program(program)

    tested.check_valid_program(program, raise_on_fail=False)
