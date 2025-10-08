from unittest.mock import patch

# flake8: noqa: F401
from pcvs.backend import run as tested  # pylint: disable=unused-import

from ..conftest import click_call
from ..conftest import isolated_fs


@patch("pcvs.backend.session.store_session_to_file", return_value={})
@patch("pcvs.backend.session.update_session_from_file", return_value={})
@patch("pcvs.backend.session.remove_session_from_file", return_value={})
def test_big_integration(rs, us, ss):  # pylint: disable=unused-argument
    with isolated_fs():
        res = click_call("profile", "create", "local.default")
        res = click_call("run")
        assert res.exit_code == 0


@patch("pcvs.backend.session")
@patch("pcvs.backend.profile.Profile")
@patch("pcvs.backend.bank")
@patch("pcvs.helpers.system")
def override(mock_sys, mock_bank, mock_pf, mock_run, caplog):  # pylint: disable=unused-argument
    with isolated_fs():
        res = click_call("run", ".")
        assert res.exit_code == 0

        res = click_call("run", ".")
        assert res.exit_code != 0
        assert "Previous run artifacts found" in caplog.text

        caplog.clear()
        _ = click_call("run", ".", "--override")
