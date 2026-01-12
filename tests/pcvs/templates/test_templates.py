from pcvs.backend.configfile import get_conf
from pcvs.helpers.storage import ConfigLocator
from pcvs.helpers.storage import ConfigScope


def test_configuration_templates():
    """Test that all configs are valides."""
    for test_desc in ConfigLocator().list_all_configs(scope=ConfigScope.GLOBAL):
        cf = get_conf(test_desc)
        cf.validate()
