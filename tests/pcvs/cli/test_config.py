import logging

import pytest

from pcvs.helpers.storage import ConfigKind
from pcvs.helpers.storage import ConfigScope

from ..conftest import click_call
from ..conftest import dummy_config_fs
from ..conftest import isolated_fs

try:
    import rich_click as click

    click.rich_click.SHOW_ARGUMENTS = True
except ImportError:
    import click


def test_cmd():
    res = click_call("config")
    assert "Usage:" in res.stdout


@pytest.mark.parametrize("config_kind", ConfigKind.all_kinds())
@pytest.mark.parametrize("config_scope", ConfigScope.all_scopes())
def test_list(config_scope: ConfigScope, config_kind: ConfigKind):
    with dummy_config_fs():
        token = ":".join([str(config_scope), str(config_kind)])
        res = click_call("config", "list", token)
        assert res.exit_code == 0


@pytest.mark.parametrize("config_scope", ConfigScope.all_scopes())
def test_list_scopes(config_scope):
    with dummy_config_fs():
        res = click_call("config", "list", str(config_scope))
        assert res.exit_code == 0


def test_list_all():
    with dummy_config_fs():
        res = click_call("config", "list")
        assert res.exit_code == 0


# theses tests may be broken
def test_list_wrong(caplog):
    caplog.set_level(logging.DEBUG)
    res = click_call("config", "list", "error")
    assert res.exit_code != 0
    assert "Invalid scope or kind" in res.stderr

    res = click_call("config", "list", "failure:compiler")
    assert res.exit_code != 0
    assert "Invalid config scope" in res.stderr

    res = click_call("config", "list", "failure:compiler:extra:field")
    assert res.exit_code != 0
    assert "Bad user token" in res.stderr


def test_show():
    # show config that exist
    with dummy_config_fs():
        res = click_call("config", "show", "local:compiler:dummy-config")
        assert res.exit_code == 0

    # show config that does not exist
    with isolated_fs():
        res = click_call("config", "show", "local:compiler:dummy-config")
        assert res.exit_code != 0


def test_create():
    # create config that does not exist
    with isolated_fs():
        res = click_call("config", "create", "local:compiler:dummy-config")
        assert res.exit_code == 0

    # create config that already exist
    with dummy_config_fs():
        res = click_call("config", "create", "local:compiler:dummy-config")
        assert res.exit_code != 0


def test_clone():
    # target already exist
    with dummy_config_fs():
        res = click_call(
            "config", "create", "local:compiler:dummy-config", "-c", "local:compiler:dummy-config"
        )
        assert res.exit_code != 0

    # source does not exist
    with dummy_config_fs():
        res = click_call(
            "config", "create", "local:compiler:some-config", "-c", "local:compiler:another"
        )
        assert res.exit_code != 0

    # source exist, target does not, everything OK
    with dummy_config_fs():
        res = click_call(
            "config", "create", "local:compiler:another", "-c", "local:compiler:dummy-config"
        )
        assert res.exit_code == 0


def test_destroy():
    # delete config that exist
    with dummy_config_fs():
        res = click_call("config", "destroy", "-f", "local:compiler:dummy-config")
        assert res.exit_code == 0

    # delete config that does not exist
    with isolated_fs():
        res = click_call("config", "destroy", "-f", "local:compiler:dummy-config")
        assert res.exit_code != 0


def test_edit():
    # edit a config that does not exist
    with isolated_fs():
        res = click_call("config", "edit", "compiler:dummy-config")
        assert res.exit_code != 0


# TODO: add test for edit config / create config with mock on click edit function
