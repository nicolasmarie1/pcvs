import os

from pcvs.helpers.system import GlobalConfig


def generate_local_variables(label, subprefix):
    """Return directories from PCVS working tree :

        - the base source directory
        - the current source directory
        - the base build directory
        - the current build directory

    :param label: name of the object used to generate paths
    :type label: str
    :param subprefix: path to the subdirectories in the base path
    :type subprefix: str
    :raises CommonException.NotFoundError: the label is not recognized as to be
        validated
    :return: paths for PCVS working tree
    :rtype: tuple
    """
    if subprefix is None:
        subprefix = ""

    base_srcdir = GlobalConfig.root['validation']['dirs'].get(label, '')
    cur_srcdir = os.path.join(base_srcdir, subprefix)
    base_buildir = os.path.join(GlobalConfig.root['validation']['output'],
                                "test_suite", label)
    cur_buildir = os.path.join(base_buildir, subprefix)

    return base_srcdir, cur_srcdir, base_buildir, cur_buildir
