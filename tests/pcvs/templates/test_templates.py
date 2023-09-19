import os
import sys

import jsonschema
import pytest
from ruamel.yaml import YAML
from ruamel.yaml import YAMLError

from pcvs.backend.config import ConfigurationBlock
from pcvs.backend.config import init as cinit
from pcvs.backend.profile import init as pinit
from pcvs.backend.profile import Profile
from pcvs.helpers.exceptions import ValidationException


def find_files(t):
    array = []
    d = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pcvs", "templates", t)
    for f in os.listdir(d):
        if f == "group-compat.yml":
            continue
        array.append(os.path.join(d, f))
    return array

def manage_validation(label, f):
    err = None
    try:
        f()
        state = "OK"
    except (ValidationException.FormatError, ValidationException.SchemeError) as e:
        state = "NOK"
        err = e.dbg
    print("* {:12}: {}".format(state, label))
    if err:
        print("\t-> {}".format(err))


@pytest.mark.parametrize("configpath", [*find_files("config")])
def test_configuration_templates(configpath):
    cinit()
    config = os.path.basename(configpath)
    conf_kind = config.split(".")[0]
    t = ConfigurationBlock(conf_kind, "test", "local")
    with open(configpath, 'r') as fh:
        data = YAML(typ='safe').load(fh)
        t.fill(data)
    manage_validation(config, t.check)

@pytest.mark.parametrize("profilepath", [*find_files("config")])
def test_profile_template(profilepath):
    pinit()    
    t = Profile("tmp", "local")
    with open(profilepath, 'r') as fh:
        data = YAML(typ='safe').load(fh)
        t.fill(data)
    manage_validation(os.path.basename(profilepath), t.check)
