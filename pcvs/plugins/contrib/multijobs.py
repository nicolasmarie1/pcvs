from pcvs.orchestration.manager import Manager
from pcvs.orchestration.set import ExecMode
from pcvs.orchestration.set import Set
from pcvs.plugins import Plugin


class SchedMultiJobs(Plugin):
    step = Plugin.Step.SCHED_SET_EVAL

    first_run_with_compilation = True

    def first_allocation(self, jobman: Manager) -> Set | None:
        the_set: Set | None = None
        for job_id, job in jobman.jobs.items():
            if "compilation" in job.tags:
                if not the_set:
                    the_set = Set(execmode=ExecMode.REMOTE)
                the_set.add(job)
                jobman.jobs.pop(job_id)
                job.pick()
        return the_set

    def run(self, *args, **kwargs) -> Set | None:  # type: ignore
        jobman: Manager = kwargs["jobman"]
        job_limit: int | None = kwargs.get("max_job_limit", None)

        if self.first_run_with_compilation:
            self.first_run_with_compilation = False
            return self.first_allocation(jobman)

        the_set: Set | None = None
        for job_id, job in jobman.jobs.items():
            if job.has_completed_deps():
                if not the_set:
                    the_set = Set(execmode=ExecMode.ALLOC)
                the_set.add(job)
                jobman.jobs.pop(job_id)
                job.pick()
                if job_limit is not None and the_set.size >= job_limit:
                    break
        return the_set
