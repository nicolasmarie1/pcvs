import pcvs

from .conftest import click_call
from .conftest import isolated_fs


def test_cmd():
    res = click_call('--help')
    assert ('Usage:' in res.stdout)


def test_version():
    res = click_call('--version')
    assert(res.exit_code == 0)
    assert ("Parallel Computing Validation System (pcvs) -- version" in res.output)


def test_bad_command():
    res = click_call('wrong_command')
    assert(res.exit_code != 0)
    assert('No such command' in res.stderr+res.stdout)
