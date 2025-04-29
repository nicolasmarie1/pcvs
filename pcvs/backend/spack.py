import subprocess

from pcvs import testing
from pcvs.helpers.system import MetaDict
from pcvs.testing.testfile import TestFile


def parse_spec_variants(specname):
    """
    From a given Spack spec, build the list of values for any declared variant.

    :param specname: the spack spec to concretize
    :type specname: str
    :return: the dict of possible values for each variants
    :rtype: Dict[str, Any]
    """
    d = dict()
    cmd = 'spack python -c \'import spack.repo; print("\\n".join(["{}:{}".format(v.name, v.allowed_values) for v in spack.repo.get("' + \
        specname + '").variants.values()]))\''
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    fds = p.communicate()
    for line in fds[0].decode().rstrip().split("\n"):
        name, val_raw = line.split(':')
        values = val_raw.split(', ')

        d[name] = {
            "option": "{}=".format(name),
            "position": "after",
            "type": "argument",
            "subtitle": "{}=".format(name),
            "values": values
        }
    return d


def generate_from_variants(package, label, prefix):
    """
    Build job to be scheduled from a given Spack package.

    :param package: Spack package name
    :type package: str
    :param label: group label name
    :type label: str
    :param prefix: subprefix name for this package
    :type prefix: str
    """
    data = MetaDict()
    dict_of_variants = parse_spec_variants(package)

    data[package].run.program = "spack install {} ".format(package)
    data[package].run.iterate.program = dict_of_variants
    data[package].run.attributes = {
        "command_wrap": False,
        "path_resolution": False,
    }

    _, src, _, build = testing.generate_local_variables(label, prefix)

    t = TestFile(file_in=src,
                 path_out=build,
                 data=data,
                 label=label,
                 prefix=prefix)
    t.process()
    t.flush_sh_file()
