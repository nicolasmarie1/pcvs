import sys

from pcvs import io
from pcvs.backend.metaconfig import GlobalConfig
from pcvs.plugins import Plugin
from pcvs.testing.test import Test

# Configuration needed to run this plugin:
# from profile configuration:
# validate:
#   analysis:
#     (not_longer_than_previous_runs is the only available right now)
#     method:
#     args:
#       history_depth: (nb of history to check in bank, default: 1)
#       tolerance: (tolerance compared to previous runs, default: 2%)
# from cli:
# validation.target_bank


class BankValidationPlugin(Plugin):
    """TODO:"""

    step = Plugin.Step.TEST_RESULT_EVAL

    def __init__(self):
        super().__init__()
        self._series = None
        self._bank_hdl = GlobalConfig.root.get_internal("bank")

    def run(self, *args, **kwargs):
        """TODO:"""
        if self._bank_hdl is None:
            return None  # Not running with a bank, stop !

        self._series = self._bank_hdl.get_series(
            self._bank_hdl.build_target_branch_name(
                hashid=GlobalConfig.root["validation"]["pf_hash"]
            )
        )
        if not self._series:
            # no history, stop !
            return None

        node = kwargs.get("analysis", {})
        job = kwargs.get("job", None)

        method = node.get("method", None)
        args = node.get("args", {})
        if method and hasattr(self, method):
            func = getattr(self, method)
            return func(args, job)
        return None

    # not longer than the average of previous runs
    def not_longer_than_previous_runs(self, args, job):
        """TODO:"""
        if not self._bank_hdl:
            return (Test.State.ERR_OTHER, 0)

        max_runs = args.get("history_depth", 1)
        if max_runs == -1:
            max_runs = sys.maxsize
        # 2% tolerace by default
        tolerance = args.get("tolerance", 2)
        min_time = sys.maxsize
        cnt = 0
        run = self._series.last
        while cnt < max_runs:
            res = run.get_data(job.name)
            if res and res.state == Test.State.SUCCESS:
                min_time = min(min_time, res.time)
                cnt += 1
            run = run.previous
            if run is None:
                break
        if cnt == 0:
            return None
        # soft_timeout = (total_time / cnt) * (1 + tolerance / 100)
        soft_timeout = min_time * (1 + (tolerance / 100))
        io.console.debug("Bank Validation Plugin: {job.time}/{soft_timeout}")
        if cnt >= 0 and job.time >= soft_timeout:
            return (Test.State.SOFT_TIMEOUT, soft_timeout)
        return None
