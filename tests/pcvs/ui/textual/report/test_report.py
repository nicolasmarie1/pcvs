# flake8: noqa: F401
from pcvs.ui.textual import report as tested  # pylint: disable=unused-import

from ....conftest import click_call
from ....conftest import isolated_fs


def test_loaded_tui():
    with isolated_fs():
        res = click_call('profile', 'create', 'local.default')
        res = click_call('run')
        res = click_call('--tui', 'report')
        assert res.exit_code == 0
