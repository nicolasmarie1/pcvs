from unittest.mock import patch

from pcvs.helpers import pm
from pcvs.helpers import system
from pcvs.testing import test as tested


@patch(
    "pcvs.helpers.system.GlobalConfig.root",
    system.MetaConfig(
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
        env=["testenv"],
        matchers={"matcher1": {"expr": "test"}},
        valscript="testvalscript",
    )
    assert test.name == "label/testsubtree/testte_name"
    assert test.command == "testcommand"
    assert not test.been_executed()
    assert test.state == tested.Test.State.WAITING
    test.save_status(test.State.EXECUTED)
    assert test.been_executed()
    testjson = test.to_json()
    assert testjson["id"]["te_name"] == test.te_name
    assert testjson["id"]["subtree"] == test.subtree
    assert testjson["id"]["fq_name"] == test.name

    test.save_final_result()
    test.generate_script("output_file.sh")
