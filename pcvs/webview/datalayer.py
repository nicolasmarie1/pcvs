import random
from typing import Any

from pcvs.backend.session import SessionState
from pcvs.testing.test import Test
from pcvs.testing.teststate import TestState


class DataRepresentation:
    """
    Data Manager from the Flask server side.

    This class manages insertion & requests to the data tree gathering test
    results from a single report server.

    the data representation looks like:

    .. code-block:: yaml

        0:
      fs-tree:
          <LABEL1>:
              __metadata: {<counts>}
              __elems:
                  <subtree1>:
                      __metadata: {<counts>}
                      __elems:
                          <te1>:
                              _metadata: {<counts>}
                              _elems: [Test(), Test(), Test()]
      tags:
          <tag1>:
              __metadata: {<counts>}
              __elems: [Test(), Test(), Test()]
      iter:
          <it_name>:
              __metadata: {<counts>}
              __elems:
                   <possible_value>:
                       __metadata: {<counts>}
                       __elems: [Test(), Test(), Test()]
      failures: [ Test(), Test(), Test()]
      # ...

    """

    def __init__(self) -> None:
        """constructor method"""
        self.rootree: dict[str, dict[str, Any]] = {}

    def __insert_in_tree(self, test: Test, node: dict[str, Any], depth: list[str]) -> None:
        """
        Insert the given test to the given subtree.

        This function can be called recursively. depth being the list of node
        names where the Test() should be inserted. The 'node' maps to the
        current node level.

        :param test: the test to insert
        :param node: a global tree intermediate node
        :param depth: list of node names to walk through
        """
        assert "__metadata" in node.keys()

        node["__metadata"]["count"][str(test.state)] += 1

        # if targeted node is reached, insert the test
        if len(depth) == 0:
            if "__elems" not in node:
                node["__elems"] = []
            node["__elems"].append(test)
        else:
            # create default for the first access + init counters to zero
            node.setdefault("__elems", {})
            node["__elems"].setdefault(
                depth[0], {"__metadata": {"count": {k: 0 for k in list(map(str, TestState))}}}
            )
            self.__insert_in_tree(test, node["__elems"][depth[0]], depth[1:])

    def insert_session(self, sid: str, session_data: dict[str, Any]) -> None:
        """
        Insert a new session into the tree.

        :param sid: the session id, will be the data key
        :param session_data: session basic infos (buildpath, state)
        """

        # if the SID already exist, a dummy one is generated.
        if sid in self.rootree:
            while sid in self.rootree:
                sid = str(random.randint(0, 10000))

        # initialize the subtree for this session
        self.rootree.setdefault(
            sid,
            {
                "fs-tree": {"__metadata": {"count": {k: 0 for k in list(map(str, TestState))}}},
                "tags": {"__metadata": {"count": {k: 0 for k in list(map(str, TestState))}}},
                "iterators": {"__metadata": {"count": {k: 0 for k in list(map(str, TestState))}}},
                "failures": {"__metadata": {"count": {k: 0 for k in list(map(str, TestState))}}},
                "state": SessionState(session_data["state"]),
                "path": session_data["buildpath"],
            },
        )

    def close_session(self, sid: str, session_data: dict[str, Any]) -> None:
        """
        Update the tree when the targeted session is completed.

        :param sid: targeted session id
        :param session_data: session infos (state)
        """
        assert sid in self.rootree
        self.rootree[sid]["state"] = session_data["state"]

    def insert_test(self, sid: str, test: Test) -> bool:
        """
        Insert a new test.

        This test is bound to a session.

        :param sid: session id
        :param test: test to insert
        :return: a boolean, True if test has been successfully inserted
        """
        # first, insert the test in the hierarchy
        label = test.label
        subtree = test.subtree
        te_name = test.te_name

        sid_tree = self.rootree[sid]
        # insert under hierarchical subtree
        self.__insert_in_tree(test, sid_tree["fs-tree"], [label, subtree, te_name])

        for tag in test.tags:
            # insert for each tag subtree
            self.__insert_in_tree(test, sid_tree["tags"], [tag])

        if test.combination:
            # insert for each combination subtree
            for iter_k, iter_v in test.combination.items():
                self.__insert_in_tree(test, sid_tree["iterators"], [iter_k, iter_v])

        if test.state != TestState.SUCCESS:
            # if failed, save it
            self.__insert_in_tree(test, sid_tree["failures"], [])
        return True

    @property
    def session_ids(self) -> list[str]:
        """
        Get list of registered session ids.

        :return: the list of know session ids
        """
        return list(self.rootree.keys())

    def get_tag_cnt(self, sid: str) -> int:
        """
        Get the number of tag for a given session.

        :param sid: session id
        :return: number of tags
        """
        return len(self.rootree[sid]["tags"]["__elems"].keys())

    def get_label_cnt(self, sid: str) -> int:
        """
        Get the number of labels for a given session.

        :param sid: session id
        :return: number of labels
        """
        return len(self.rootree[sid]["fs-tree"]["__elems"].keys())

    def get_test_cnt(self, sid: str) -> int:
        """
        Get the number of tests for a given session.

        :param sid: session id
        :return: number of tests
        """
        return sum(self.rootree[sid]["fs-tree"]["__metadata"]["count"].values())

    def get_root_path(self, sid: str) -> str:
        """
        For a session, get the build path where data are stored.

        :param sid: session id
        :return: build path
        """
        path = self.rootree[sid]["path"]
        assert isinstance(path, str)
        return path

    def get_token_content(self, sid: str, token: str) -> Any:
        """
        Advanced function to access partial data tree.

        :param sid: session id
        :param token: subtree name to access to
        :return: the whole data tree segment, empty dict if not found
        """
        if token not in self.rootree[sid]:
            return {}

        return self.rootree[sid][token]

    def extract_tests_under(self, node: dict[str, Any]) -> list[str]:
        """
        Retrieve all tests undef a given data tree subnode.

        :param node: data subnode
        :return: list of tests under this subnode
        """
        assert "__elems" in node.keys()
        elements = node["__elems"]

        if isinstance(elements, list):
            return [str(x.to_json(strstate=True)) for x in elements if isinstance(x, Test)]

        if isinstance(elements, dict):
            ret = []
            for elt in elements.values():
                ret += self.extract_tests_under(elt)
            return ret
        assert False

    def get_sessions(self) -> list[dict[str, Any]]:
        """
        Get the list of current known sessions.

        :return: a dict mapping to session infos.
        """
        return [
            {
                "path": v["path"],
                "state": str(SessionState(v["state"])),
                "sid": k,
                "count": v["fs-tree"]["__metadata"]["count"],
            }
            for k, v in self.rootree.items()
        ]
