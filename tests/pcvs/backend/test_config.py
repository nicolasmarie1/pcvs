import os
from pathlib import Path
from unittest.mock import patch

from pcvs.helpers.storage import ConfigKind
from pcvs.helpers.storage import ConfigLocator
from pcvs.helpers.storage import ConfigScope

from ..conftest import dummy_fs_profiles_in_tmp


def test_config_scopes():
    """Check that config are correctly found at the right scope."""
    with dummy_fs_profiles_in_tmp() as (glob, user, local):
        cl = ConfigLocator()
        scopes_to_paths = {
            ConfigScope.GLOBAL: glob,
            ConfigScope.USER: user,
            ConfigScope.LOCAL: local,
        }
        with patch.object(cl, "_storage_scope_paths", new=scopes_to_paths):
            for k in ConfigKind.all_kinds():
                for s in ConfigScope.all_scopes():
                    confs = cl.list_configs(k, s)
                    print(f"test: {str(k)}, {str(s)}")
                    assert len(confs) == 1
                    assert confs[0].path == Path(
                        os.path.join(
                            scopes_to_paths[s], str(k), f"default{ConfigKind.get_file_ext(k)}"
                        )
                    )
