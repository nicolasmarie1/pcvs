from ..conftest import click_call
from ..conftest import dummy_profile_fs


def test_check_profiles():
    with dummy_profile_fs():
        res = click_call("check", "--profiles")
        assert "Valid" in res.stdout
        assert "Everything is OK!" in res.stdout


def test_check_configs():
    with dummy_profile_fs():
        res = click_call("check", "--configs")
        assert "Valid" in res.stdout
        assert "Everything is OK!" in res.stdout


def test_check_directory():
    with dummy_profile_fs():
        click_call("check", "--directory", ".")
