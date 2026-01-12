import os

import pytest

import pcvs
from pcvs.backend import bank as tested
from pcvs.helpers import git
from pcvs.helpers import utils

from ..conftest import dummy_run_fs
from ..conftest import isolated_fs


@pytest.fixture
def dummy_run():
    with dummy_run_fs() as path:
        yield path


@pytest.fixture
def mock_repo_fs():
    with isolated_fs() as tmp:
        path = os.path.join(tmp, "fake_bank")
        os.makedirs(path)
        yield path


def test_bank_connect(mock_repo_fs):  # pylint: disable=redefined-outer-name
    # first test with a specific dir to create the Git repo
    pcvs.io.init()
    obj = tested.Bank(mock_repo_fs)
    obj.connect()
    assert os.path.isfile(os.path.join(mock_repo_fs, "HEAD"))
    obj.disconnect()

    # Then use the recursive research to let pygit2 detect the Git repo
    obj = tested.Bank(mock_repo_fs)
    obj.connect()
    assert obj.prefix == mock_repo_fs  # pygit2 should detect the old repo
    assert os.path.isfile(os.path.join(mock_repo_fs, "HEAD"))
    obj.connect()  # ensure multiple connection are safe
    obj.disconnect()


def test_save_run(mock_repo_fs, dummy_run, capsys):  # pylint: disable=redefined-outer-name
    pcvs.io.init()
    obj = tested.Bank(f"original-tag@{mock_repo_fs}")
    obj.connect()
    prefix = utils.find_buildir_from_prefix(dummy_run)
    obj.save_from_buildir("override-tag", prefix)
    assert obj.get_count() == 1

    obj.save_from_buildir(None, prefix)
    assert obj.get_count() == 2

    assert len(obj.list_series("override-tag")) == 1
    assert len(obj.list_series("original-tag")) == 1
    obj.show()
    capture = capsys.readouterr()
    assert "original-tag: 1 distinct testsuite(s)" in capture.out
    assert "override-tag: 1 distinct testsuite(s)" in capture.out
    obj.disconnect()

    repo = git.elect_handler(mock_repo_fs)
    repo.open()
    assert len(list(repo.branches())) == 3
