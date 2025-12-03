import os
from pathlib import Path

import pytest

import pcvs
from pcvs import PATH_INSTDIR
from pcvs.backend.config import Config
from pcvs.backend.configfile import YmlConfigFile
from pcvs.backend.metaconfig import MetaConfig
from pcvs.helpers import pm
from pcvs.helpers.storage import ConfigDesc
from pcvs.helpers.storage import ConfigKind
from pcvs.helpers.storage import ConfigScope


def test_bootstrap_compiler():
    obj = MetaConfig()
    obj.bootstrap_compiler(
        Config(
            {
                "compilers": {
                    "cc": {
                        "program": "/path/to/cc",
                        "variants": {
                            "openmp": {
                                "args": "-fopenmp",
                            },
                        },
                    }
                },
                "package_manager": {
                    "spack": ["mypackage@myversion"],
                    "module": ["mod1", "mod2"],
                },
            },
        )
    )
    assert isinstance(obj["compiler"], Config)
    assert obj["compiler"]["compilers"]["cc"]["program"] == "/path/to/cc"
    assert obj["compiler"]["compilers"]["cc"]["variants"]["openmp"]["args"] == "-fopenmp"

    assert isinstance(obj["compiler"]["package_manager"]["spack"], list)
    assert len(obj["compiler"]["package_manager"]["spack"]) == 1
    assert isinstance(obj["compiler"]["package_manager"]["module"], list)
    assert len(obj["compiler"]["package_manager"]["module"]) == 2

    package_array = obj.get_internal("cc_pm")
    res = {}
    assert isinstance(package_array, list)
    assert len(package_array) == 3
    for p in package_array:
        assert isinstance(p, pm.PManager)
        if type(p) in res:
            res[type(p)] += 1
        else:
            res[type(p)] = 1
    assert res[pm.SpackManager] == 1
    assert res[pm.ModuleManager] == 2


def test_bootstrap_runtime():
    obj = MetaConfig()
    obj.bootstrap_runtime(
        Config(
            {
                "program": "/path/to/rt",
                "criterions": {
                    "n_mpi": {
                        "numeric": True,
                    },
                },
                "package_manager": {
                    "spack": ["mypackage@myversion"],
                    "module": ["mod1", "mod2"],
                },
            },
        )
    )
    assert isinstance(obj["runtime"], Config)
    assert obj["runtime"]["program"] == "/path/to/rt"
    assert obj["runtime"]["criterions"]["n_mpi"]["numeric"]

    assert isinstance(obj["runtime"]["package_manager"]["spack"], list)
    assert len(obj["runtime"]["package_manager"]["spack"]) == 1
    assert isinstance(obj["runtime"]["package_manager"]["module"], list)
    assert len(obj["runtime"]["package_manager"]["module"]) == 2

    package_array = obj.get_internal("rt_pm")
    res = {}
    assert isinstance(package_array, list)
    assert len(package_array) == 3
    for p in package_array:
        assert isinstance(p, pm.PManager)
        if type(p) in res:
            res[type(p)] += 1
        else:
            res[type(p)] = 1
    assert res[pm.SpackManager] == 1
    assert res[pm.ModuleManager] == 2


@pytest.fixture
def kw_keys():
    return [
        f.replace("-scheme.yml", "")
        for f in os.listdir(os.path.join(PATH_INSTDIR, "schemes/generated/"))
    ]


@pytest.fixture
def init_config():
    d = {"": "value1", "key2": "value2"}
    Config(d)


def test_validate(kw_keys):  # pylint: disable=unused-argument,redefined-outer-name
    compiler = {
        "compilers": {
            "cc": {
                "program": "example",
                "variants": {
                    "openmp": {"args": "example"},
                    "tbb": {"args": "example"},
                    "cuda": {"args": "example"},
                    "strict": {"args": "example"},
                },
            },
            "cxx": {"program": "example"},
            "fc": {"program": "example"},
            "f77": {"program": "example"},
            "f90": {"program": "example"},
        },
        "package_manager": {"spack": ["example"], "module": ["example"]},
    }
    runtime = {
        "program": "example",
        "args": "example",
        "criterions": {
            "iterator_name": {
                "option": "example",
                "numeric": True,
                "type": "argument",
                "position": "before",
                "aliases": {
                    "ib": "example",
                    "tcp": "example",
                    "shmem": "example",
                    "ptl": "example",
                },
            }
        },
        "package_manager": {"spack": ["example"], "module": ["example"]},
    }
    criterion = {
        "example": {"values": [1, 2], "subtitle": "example"},
    }
    criterion_wrong = {
        "wrong-key": {
            "example": {"values": [1, 2], "subtitle": "example"},
        },
    }
    keywords = [
        (compiler, ConfigKind.COMPILER),
        (runtime, ConfigKind.RUNTIME),
        (criterion, ConfigKind.CRITERION),
    ]
    for kw in keywords:
        conf = YmlConfigFile(ConfigDesc("test", Path("test"), kw[1], ConfigScope.LOCAL))
        conf.from_dict(kw[0])
    with pytest.raises(pcvs.helpers.exceptions.ValidationException.FormatError):
        conf = YmlConfigFile(
            ConfigDesc("test", Path("test"), ConfigKind.CRITERION, ConfigScope.LOCAL)
        )
        conf.from_dict(criterion_wrong)


def test_config(init_config):  # pylint: disable=unused-argument,redefined-outer-name
    pass
