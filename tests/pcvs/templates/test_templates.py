# import os
# from pathlib import Path
#
# import pytest
#
# from pcvs.backend.configfile import ConfigFile
# from pcvs.backend.profile import Profile
# from pcvs.helpers.storage import ConfigDesc
# from pcvs.helpers.storage import ConfigKind
# from pcvs.helpers.storage import ConfigScope

# TODO re enable template tests
# def find_files(t):
#     array = []
#     d = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pcvs", "templates", t)
#     for f in os.listdir(d):
#         if f == "group-compat.yml":
#             continue
#         array.append(os.path.join(d, f))
#     return array
#
#
# @pytest.mark.parametrize("configpath", [*find_files("config")])
# def test_configuration_templates(configpath):
#     config = os.path.basename(configpath)
#     conf_kind = ConfigKind.fromstr(config.split(".")[0])
#     _ = ConfigFile(ConfigDesc("test", Path(configpath), conf_kind, ConfigScope.LOCAL))
#
#
# @pytest.mark.parametrize("profilepath", [*find_files("profile")])
# def test_profile_template(profilepath):
#     _ = Profile(ConfigDesc("tmp", Path(profilepath), ConfigKind.PROFILE, ConfigScope.LOCAL))
#
