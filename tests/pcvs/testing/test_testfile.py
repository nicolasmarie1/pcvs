import getpass
import os
import pathlib
from unittest.mock import patch

import pytest
from ruamel.yaml import YAML

from pcvs.backend.metaconfig import GlobalConfig
from pcvs.backend.metaconfig import MetaConfig
from pcvs.helpers import pm
from pcvs.orchestration import Orchestrator
from pcvs.orchestration.publishers import BuildDirectoryManager
from pcvs.plugins import Collection
from pcvs.testing import testfile as tested
from tests.pcvs.conftest import isolated_fs


def test_replace_tokens():
    build = "/path/to/build"
    prefix = "dir1/dir2"
    src = "/path/to/src"

    assert (
        tested.replace_special_token("build curdir is @BUILDPATH@", src, build, prefix)
        == "build curdir is /path/to/build/dir1/dir2"
    )

    assert (
        tested.replace_special_token("src curdir is @SRCPATH@", src, build, prefix)
        == "src curdir is /path/to/src/dir1/dir2"
    )

    assert (
        tested.replace_special_token("src rootdir is @ROOTPATH@", src, build, prefix)
        == "src rootdir is /path/to/src"
    )

    assert (
        tested.replace_special_token("build rootdir is @BROOTPATH@", src, build, prefix)
        == "build rootdir is /path/to/build"
    )

    assert tested.replace_special_token(
        "HOME is @HOME@", src, build, prefix
    ) == "HOME is {}".format(pathlib.Path.home())

    assert tested.replace_special_token(
        "USER is @USER@", src, build, prefix
    ) == "USER is {}".format(getpass.getuser())


@pytest.fixture
def isolated_yml_test():
    testyml = {
        "test_MPI_2INT": {
            "build": {
                "files": "'@SRCPATH@/constant.c'",
                "sources": {
                    "binary": "test_MPI_2INT",
                    "cflags": "-DSYMB=MPI_2INT -DTYPE1='int' -DTYPE='int'",
                },
            },
            "group": "GRPSERIAL",
            "run": {"program": "test_MPI_2INT"},
            "tag": ["std_1", "constant"],
        }
    }
    with isolated_fs():
        path = os.getcwd()
        testdir = "test-dir"
        os.makedirs(testdir)
        with open(os.path.join(path, testdir, "pcvs.yml"), "w", encoding="utf-8") as fh:
            YAML(typ="safe").dump(testyml, fh)
        yield path
    # utils.delete_folder(testdir)


@patch(
    "pcvs.backend.metaconfig.GlobalConfig.root",
    MetaConfig(
        {
            "compiler": {
                "compilers": {
                    "cc": {
                        "program": "/path/to/cc",
                        "extension": ".*\\.c",
                        "variants": {
                            "openmp": {
                                "args": "-fopenmp",
                            },
                        },
                    }
                },
            },
            "group": {},
            "criterion": {
                "n_mpi": {
                    "numeric": True,
                    "values": [1, 2, 4],
                    "subtitle": "mpi",
                },
            },
            "runtime": {},
            "machine": {},
            "validation": {
                "output": "test_output",
                "dirs": {"keytestdir": "valuetestdir"},
            },
        },
        {
            "cc_pm": [pm.SpackManager("fakespec")],
            "pColl": Collection(),
        },
    ),
)
@patch.dict(os.environ, {"HOME": "/home/user", "USER": "superuser"})
# @patch("pcvs.testing.tedesc.TEDescriptor", autospec=True)
def test_TestFile(isolated_yml_test):  # pylint: disable=redefined-outer-name
    # orcherstrator use global config to setup, so it need to be added at runtime
    # after GlobalConfig have already been initialize.
    with isolated_fs():
        GlobalConfig.root.set_internal("build_manager", BuildDirectoryManager())
        GlobalConfig.root.set_internal("orchestrator", Orchestrator())
        testfile = tested.TestFile(
            os.path.join(isolated_yml_test, "test-dir/pcvs.yml"),
            os.path.dirname(isolated_yml_test),
            label="keytestdir",
            prefix=".",
        )
        testfile.load_from_file()
        testfile.process()
        testfile.generate_debug_info()
        testfile.flush_sh_file()
