import os
import stat
from datetime import datetime
from unittest.mock import patch

import pytest
from click.testing import CliRunner

import pcvs
from pcvs.backend import run as tested
from pcvs.backend.metaconfig import GlobalConfig
from pcvs.backend.metaconfig import MetaConfig
from pcvs.helpers.exceptions import ValidationException
from pcvs.plugins import Collection
from pcvs.testing.tedesc import TEDescriptor

GOOD_CONTENT = """#!/bin/sh
echo 'test_node:'
echo '  build:'
echo '    sources:'
echo '      binary: "a.out"'
"""

BAD_OUTPUT = """#!/bin/sh
echo "test_node:"
echo "  unknown_node: 'test'"
"""

BAD_SCRIPT = """#!/bin/sh
echo "failure"
exit 42
"""


def help_create_setup_file(path, s):
    os.makedirs(os.path.dirname(path))
    with open(path, "w") as fh:
        fh.write(s)
    os.chmod(path, stat.S_IRUSR | stat.S_IXUSR)


@pytest.fixture
def mock_config():
    with CliRunner().isolated_filesystem():
        with patch.object(
            GlobalConfig,
            "root",
            MetaConfig(
                {
                    "compiler": {"compilers": {}},
                    "criterion": {},
                    "validation": {
                        "output": os.getcwd(),
                        "dirs": {"L1": os.getcwd()},
                        "datetime": datetime.now(),
                        "buildcache": os.path.join(os.getcwd(), "buildcache"),
                    },
                },
                {"pColl": Collection()},
            ),
        ):
            yield {}


def test_process_setup_scripts(mock_config):  # pylint: disable=unused-argument,redefined-outer-name
    d = os.path.join(GlobalConfig.root["validation"]["dirs"]["L1"], "subtree")
    f = os.path.join(d, "pcvs.setup")
    help_create_setup_file(f, GOOD_CONTENT)
    pcvs.io.init()
    with patch("pcvs.testing.tedesc.TEDescriptor") as _:
        tested.process_dyn_setup_scripts([("L1", "subtree", "pcvs.setup")])


def test_process_bad_setup_script(
    mock_config,
):  # pylint: disable=unused-argument,redefined-outer-name
    d = os.path.join(GlobalConfig.root["validation"]["dirs"]["L1"], "subtree")
    f = os.path.join(d, "pcvs.setup")
    help_create_setup_file(f, BAD_SCRIPT)
    pcvs.io.init()
    try:
        tested.process_dyn_setup_scripts([("L1", "subtree", "pcvs.setup")])
    except ValidationException.SetupError:
        pass


def test_process_wrong_setup_script(
    mock_config,
):  # pylint: disable=unused-argument,redefined-outer-name
    d = os.path.join(GlobalConfig.root["validation"]["dirs"]["L1"], "subtree")
    f = os.path.join(d, "pcvs.setup")
    help_create_setup_file(f, BAD_OUTPUT)
    pcvs.io.init()
    TEDescriptor.init_system_wide("n_node")
    try:
        tested.process_dyn_setup_scripts([("L1", "subtree", "pcvs.setup")])
    except ValidationException.FormatError:
        pass
