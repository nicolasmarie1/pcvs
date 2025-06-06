import getpass
import os
import pathlib
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from ruamel.yaml import YAML

import pcvs
from pcvs import NAME_BUILDIR
from pcvs import PATH_INSTDIR
from pcvs.helpers import log
from pcvs.helpers import pm
from pcvs.helpers import system
from pcvs.plugins import Collection
from pcvs.testing import testfile as tested


def test_replace_tokens():
    build = "/path/to/build"
    prefix = "dir1/dir2"
    src = "/path/to/src"

    assert(tested.replace_special_token(
                'build curdir is @BUILDPATH@',
                src, build, prefix
    ) == 'build curdir is /path/to/build/dir1/dir2')

    assert(tested.replace_special_token(
                'src curdir is @SRCPATH@',
                src, build, prefix
    ) == 'src curdir is /path/to/src/dir1/dir2')

    assert(tested.replace_special_token(
                'src rootdir is @ROOTPATH@',
                src, build, prefix
    ) == 'src rootdir is /path/to/src')

    assert(tested.replace_special_token(
                'build rootdir is @BROOTPATH@',
                src, build, prefix
    ) == 'build rootdir is /path/to/build')

    assert(tested.replace_special_token(
                'HOME is @HOME@',
                src, build, prefix
    ) == 'HOME is {}'.format(pathlib.Path.home()))

    assert(tested.replace_special_token(
                'USER is @USER@',
                src, build, prefix
    ) == 'USER is {}'.format(getpass.getuser()))


@pytest.fixture
def isolated_yml_test():
    testyml = {
        "test_MPI_2INT":{
            "build":{
                "files": "'@SRCPATH@/constant.c'",
                "sources": {
                    "binary": "test_MPI_2INT",
                    "cflags": "-DSYMB=MPI_2INT -DTYPE1='int' -DTYPE='int'",
                }
            },
            "group": "GRPSERIAL",
            "run":{
                "program": "test_MPI_2INT"
            },
            "tag": [
                "std_1",
                "constant"
            ]
        }
    }
    with CliRunner().isolated_filesystem():
        path = os.getcwd()
        testdir = "test-dir"
        os.makedirs(testdir)
        with open(os.path.join(path, testdir, "pcvs.yml"), "w") as fh:
            YAML(typ='safe').dump(testyml, fh)
        yield path
    # utils.delete_folder(testdir)


@patch("pcvs.helpers.system.MetaConfig.root", system.MetaConfig({
    "_MetaConfig__internal_config": {
        "cc_pm": [pm.SpackManager("fakespec")],
        "pColl": Collection()
    },
    "validation": {
        "output": "test_output",
        "dirs": {
            "keytestdir": "valuetestdir"
        }
    }
}))
@patch.dict(os.environ, {'HOME': '/home/user', 'USER': 'superuser'})
@patch("pcvs.testing.tedesc.TEDescriptor", autospec=True)
def test_TestFile(tedesc, isolated_yml_test):
    def dummydesc():
        pass
    tedesc.construct_tests = dummydesc
    testfile = tested.TestFile(os.path.join(isolated_yml_test, "test-dir/pcvs.yml"), 
        os.path.dirname(isolated_yml_test), 
        label="keytestdir", 
        prefix=".")
    testfile.process()
    testfile.generate_debug_info()
    testfile.flush_sh_file()
