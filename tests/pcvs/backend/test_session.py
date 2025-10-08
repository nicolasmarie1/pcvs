import hashlib
import os
from datetime import datetime
from unittest import mock
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from ruamel.yaml import YAML

import pcvs
from pcvs.backend import session as tested


def dummy_main_function(arg_a, arg_b):
    assert arg_a == "argument_a"
    assert arg_b == ["argument_b"]


@pytest.fixture
def mock_home_config():
    with CliRunner().isolated_filesystem():
        mock.patch.object(pcvs, "PATH_SESSION", os.path.join(os.getcwd(), "sessions"))


def test_session_init():
    date = datetime.now()
    obj = tested.Session(date)
    assert str(obj.state) == "WAITING"
    assert obj.property("started") == date


def test_session_file():
    with CliRunner().isolated_filesystem():
        date = datetime.now()
        session = {"path": os.getcwd(), "started": date}

        with patch.object(tested, "PATH_SESSION", os.getcwd()) as mock_session:
            session_id = tested.store_session_to_file(session)
            assert os.path.isfile(os.path.join(mock_session, "{}.yml".format(session_id)))
            assert session_id == tested.session_file_hash(session)
            assert (
                session_id
                == hashlib.sha1(
                    "{}:{}".format(session["path"], session["started"]).encode()
                ).hexdigest()
            )

            with open(os.path.join(mock_session, "{}.yml".format(session_id)), "r") as fh:
                data = YAML().load(fh)
                assert len(data.keys()) == 2
                assert data["path"] == os.getcwd()
                assert data["started"] == date

            sessions = tested.list_alive_sessions()
            assert len(sessions) == 1
            assert session_id in sessions

            end_date = datetime.now()
            tested.update_session_from_file(session_id, {"ended": end_date})

            with open(os.path.join(mock_session, "{}.yml".format(session_id)), "r") as fh:
                data = YAML().load(fh)
                assert len(data.keys()) == 3
                assert data["path"] == os.getcwd()
                assert data["started"] == date
                assert data["ended"] == end_date

            tested.remove_session_from_file(session_id)
            assert not os.path.exists(os.path.join(mock_session, "{}.yml".format(session_id)))
