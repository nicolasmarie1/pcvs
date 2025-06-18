import os
from unittest.mock import patch

import pytest

from pcvs.helpers import criterion
from pcvs.helpers import exceptions
from pcvs.helpers import pm
from pcvs.helpers import system
from pcvs.plugins import Collection
from pcvs.testing import tedesc as tested


@patch('pcvs.helpers.pm.identify')
def test_handle_job_deps(mock_id):
    assert (tested.build_job_deps(
                {'depends_on': ['a', 'b', 'c']}, "label", "prefix")
            == ["label/prefix/a", "label/prefix/b", "label/prefix/c"])

    assert (tested.build_job_deps(
                {'depends_on': ['/a', '/b', '/c']}, "label", "prefix")
            == ["/a", "/b", "/c"])

    mock_id.return_value = ["spack..p1", "spack..p1c2", "spack..p1p3%c4"]
    assert (len(
        tested.build_pm_deps(
            {'package_manager': {'spack': ['p1', 'p1@c2', 'p1 p3 %c4']}}
        )) == 3)

    assert len(tested.build_job_deps({}, "", "")) == 0


@patch.dict(os.environ, {'HOME': '/home/user', 'USER': 'superuser'})
@patch("pcvs.helpers.system.GlobalConfig.root",
       system.MetaConfig(
        {
            "validation": {
                "output": "test_output",
                "dirs": {
                    "label": "/this/directory"
                }
            },
            "group": {
                "GRPSERIAL": {}
            },
            "compiler": {
                "compilers": {
                    "cc": {'program': "/path/to/cc", "extension": "\\.c$"}
                }
            },
            "runtime": {"criterion": {
                "n_mpi": {"option": "-n ", "numeric": True, "values": [1, 2, 3, 4]}}
            }
        },
        {
            "cc_pm": pm.SpackManager("this_is_a_test"),
            'pColl': Collection(),
        }
       ))
def test_tedesc_regular():
    criterion.initialize_from_system()
    tested.TEDescriptor.init_system_wide("n_node")
    node = {
            "build": {
                "files": "@SRCPATH@/constant.c",
                "sources": {
                    "binary": "test_MPI_2INT",
                    "cflags": "-DSYMB=MPI_2INT -DTYPE1='int' -DTYPE='int'"
                }
            },
            "group": "GRPSERIAL",
            "run": {
                "program": "test_MPI_2INT",
                "iterate": {
                    "n_mpi": {
                        "values": [1, 2, 3, 4]
                    }
                },
            },
            "tag": [
                "std_1",
                "constant"
            ]
        }
    tedesc = tested.TEDescriptor("te_name", node, "label", "subtree")

    assert tedesc.name == "te_name"
    for i in tedesc.construct_tests():
        print(i.command)

    with pytest.raises(exceptions.TestException.TestExpressionError):
        tested.TEDescriptor("te_name", "bad_type", "label", "subtree")

        tested.TEDescriptor(
                "te_name",
                {"build": {"unknown_key": 2}},
                "label",
                "subtree")


@patch.dict(os.environ, {'HOME': '/home/user', 'USER': 'superuser'})
@patch("pcvs.helpers.system.GlobalConfig.root", system.MetaConfig(
    {
        "validation": {
            "output": "test_output",
            "dirs": {
                "label": "/this/directory"
            }
        },
        "group": {
            "GRPSERIAL": {}
        },
        "compiler": {
            "compilers": {
                "cc": {'program': "/path/to/cc", "extension": "\\.c$"}
            },
        },
        "runtime": {
            "criterion": {
                "n_mpi": {
                    "option": "-n ",
                    "numeric": True,
                    "values": [1, 2, 3, 4]
                }
            }
        }
    },
    {
        "cc_pm": pm.SpackManager("this_is_a_test"),
    }
    ))
def test_tedesc_compilation():
    criterion.initialize_from_system()
    tested.TEDescriptor.init_system_wide("n_node")
    dict_of_tests = [
        {"build": {
            "files": ["a.c", "b.c"],
            "sources": {
                "binary": "a.out"
            }
        }},
        {"build": {
            "files": "@SRCPATH@/Makefile",
            "make": {
                "target": "all"
            }
        }},
        {"build": {
            "files": ["@BUIDLPATH@/configure"],
            "autotools": {
                "autogen": True,
            },
        }},
        {"build": {
            "files": "@SRCPATH@/CMakeLists.txt",
            "cmake": {
                "vars": ['CMAKE_VERBOSE_MAKEFILE=ON']
            }
        }}
    ]
    for node in dict_of_tests:
        tedesc = tested.TEDescriptor("te_name", node, "label", "subtree")
        assert tedesc.name == "te_name"
        for i in tedesc.construct_tests():
            print(i.command)


# Sincelanguage support have been replace by compiler definition
# this test does not make sense any more.
# TODO: replace this test with a test of user define compilers in test file.
#@patch("pcvs.helpers.system.GlobalConfig.root", system.MetaConfig(
#    {
#        "validation": {
#            "output": "test_output",
#            "dirs": {
#                "label": "/this/directory"
#            }
#        },
#        "group": {
#            "GRPSERIAL": {}
#        },
#        "compiler": {
#            "compilers": {
#                "cc": {'program': "/path/to/cc", "extension": "\\.c$"},
#                "fc": {'program': "/path/to/fc", "extension": "\\.f$"},
#            },
#        },
#        "runtime": {
#            "criterion": {
#                "n_mpi": {
#                    "option": "-n ",
#                    "numeric": True,
#                    "values": [1, 2, 3, 4]
#                }
#            }
#        }
#    },
#    {
#        "cc_pm": pm.SpackManager("this_is_a_test"),
#    }
#))
#def test_te_user_defined_language():
#    node = {
#        "build": {
#            "files": "unknown_file.ext",
#            "sources": {}
#        }
#    }
#    scenarios = [
#        (["cc"], "cc"),
#        (["cc", "cxx"], "cc"),
#        (["fc", "f08"], "fc"),
#        (["cxx"], "cc"),
#    ]
#    for elt in scenarios:
#        node['build']['sources']['lang'] = elt[0]
#        tedesc = tested.TEDescriptor("te_name", node, "label", "subtree")
#        for job in tedesc.construct_tests():
#            assert job.command.startswith("/path/to/{} ".format(elt[1]))
