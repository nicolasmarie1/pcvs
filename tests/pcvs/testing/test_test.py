from unittest.mock import patch

from pcvs.backend.metaconfig import MetaConfig
from pcvs.helpers import pm
from pcvs.testing import test as tested
from pcvs.testing.test import TestState


@patch(
    "pcvs.backend.metaconfig.GlobalConfig.root",
    MetaConfig(
        {
            "validation": {
                "output": "test_output",
                "dirs": {"keytestdir": "valuetestdir"},
            },
            "group": {"GRPSERIAL": {}},
            "criterion": {},
        },
        {
            "cc_pm": "test_cc_pm",
        },
    ),
)
def test_test():
    test = tested.Test(
        label="label",
        tags=None,
        artifacts={},
        command="testcommand",
        te_name="testte_name",
        subtree="testsubtree",
        wd="testchdir",
        job_deps=["testdep"],
        mod_deps=[pm.SpackManager("recipe")],
        environment=["testenv=test"],
        validation={
            "match": {
                "matcher1": {
                    "expr": "test",
                    "expect": True,
                },
            },
            "script": {
                "path": "testvalscript",
            },
        },
    )
    assert test.name == "label/testsubtree/testte_name"
    assert test.command == "testcommand"
    assert not test.been_executed()
    assert test.state == tested.TestState.WAITING
    test.save_status(TestState.EXECUTED)
    assert not test.been_executed()
    test.save_status(TestState.SUCCESS)
    assert test.been_executed()
    testjson = test.to_json()
    assert testjson["id"]["te_name"] == test.te_name
    assert testjson["id"]["subtree"] == test.subtree
    assert testjson["id"]["fq_name"] == test.name

    test.save_final_result()
    test.generate_script("output_file.sh")
