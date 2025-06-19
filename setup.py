# add -dirty if staged area is not empty
import os

import setuptools

with open(os.path.join("version.txt"), encoding='utf-8') as fh:
    version = fh.readline()[:-1]  # remove \n

try:
    import sh

    # pylint fail to parse sh.git function correctly
    version += "+{}".format(sh.git("rev-parse", "HEAD").strip()[:8])  # pylint: disable=too-many-function-args
    if sh.git('--no-pager', 'diff', 'HEAD'):  # pylint: disable=too-many-function-args
        version += ".dirty"
except Exception:
    pass

setuptools.setup(
    version=version,
)
