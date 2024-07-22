import os
from unittest.mock import patch

import pcvs
from pcvs.ui.textual import report as tested

from .conftest import click_call
from .conftest import isolated_fs


#def test_loaded_tui():
#    with isolated_fs():
#        res = click_call('profile', 'create', 'local.default')
#        res = click_call('run')
#        res = click_call('--tui', 'report')
#        print(res.stderr)
#        assert(res.exit_code == 0)
