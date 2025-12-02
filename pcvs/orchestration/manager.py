from pcvs import io
from pcvs.backend.metaconfig import GlobalConfig
from pcvs.helpers.exceptions import OrchestratorException
from pcvs.helpers.resource_tracker import ResourceTracker
from pcvs.orchestration.publishers import ResultFileManager
from pcvs.orchestration.set import Set
from pcvs.plugins import Plugin
from pcvs.testing.test import Test
from pcvs.testing.teststate import TestState


class Manager:
    """Gather and manipulate Jobs under a hiararchical architecture.

    A Manager is in charge of carrying jobs during the scheduling. Jobs are
    divided hierarchicaly (basically, depending on the number of resource
    requested to be run). To extract jobs to be scheduled, a Manager will create
    Set()s. Once completed Sets are merged to the Manager before publishing the
    results.
    """

    def __init__(self, max_nodes: int = 0, publisher: ResultFileManager | None = None):
        """
        Initialize  a Job Manager.

        :param max_nodes: max number of nodes allowed to schedule.
        :type max_nodes: int
        :param publisher: requested publisher by the orchestrator
        :type publisher: :class:`ResultFileManager`
        """
        self._comman = GlobalConfig.root.get_internal("comman")
        self._plugin = GlobalConfig.root.get_internal("pColl")
        self._concurrent_level = GlobalConfig.root["machine"].get("concurrent_run", 1)

        self._max_nodes = max_nodes

        # job_id to Job bindings
        self.jobs: dict[str, Test] = {}
        # job dependency rules
        self.dep_rules: dict = {}

        self._publisher = publisher
        self._count = {"total": 0, "executed": 0}

    @property
    def nb_max_nodes(self) -> int:
        """Get max number of nodes.

        :return: the max nb nodes
        :rtype: int
        """
        return self._max_nodes

    @property
    def get_jobs(self) -> dict[str, Test]:
        return self.jobs

    def __add_job(self, job: Test) -> None:
        self.jobs[job.jid] = job

    def add_job(self, job: Test) -> None:
        """Store a new job to the Job Queue, the Manager table,
            save the test dependency rules and count it.

        :param job: The job to append
        :type job: :class:`Test`
        """
        # if test is not know yet, add + increment
        if job.jid not in self.jobs:
            self.__add_job(job)
            self._count["total"] += 1
            self.save_dependency_rule(job.basename, job)

    def save_dependency_rule(self, pattern: str, jobs: Test | list[Test]) -> None:
        assert isinstance(pattern, str)

        if not isinstance(jobs, list):
            jobs = [jobs]

        self.dep_rules.setdefault(pattern, [])
        self.dep_rules[pattern] += jobs

    def get_count(self, tag: str = "total") -> int:
        """Access to a particular counter.

        :param tag: a specific counter to target, defaults to "total"
        :type tag: str
        :return: a count
        :rtype: int
        """
        return self._count[tag] if tag in self._count else 0

    def resolve_deps(self) -> None:
        """Resolve the whole dependency graph.

        This function is meant to be called once and browse every single tests
        to resolve dep names to their real associated object.
        """
        for _, job in self.jobs.items():
            self.resolve_single_job_deps(job, [])

    def print_dep_graph(self, outfile_name: str | None = None) -> None:
        s = ["digraph D {"]
        for _, job in self.jobs.items():
            for d in job.get_dep_graph().keys():
                s.append(f'"{job.name}"->"{d}";')
        s.append("}")

        if not outfile_name:
            print("\n".join(s))
        else:
            with open(outfile_name, "w") as fh:
                fh.write("\n".join(s))

    def resolve_single_job_deps(self, job: Test, seen_deps: list[str]) -> None:
        """Resolve the dependency graph for a single test.

        The 'chain' argument contains list of "already-seen" dependency, helping
        to detect circular deps.

        :raises UndefDependencyError: a depname does not have a related object
        :raises CircularDependencyError: a circular dep is detected from this
            job.
        :param job: the job to resolve
        :type job: :class:`Test`
        :param chain: list of already-seen jobs during this walkthrough
        :type chain: list
        """
        seen_deps.append(job.name)
        for depname in job.job_depnames:

            hashed_dep = Test.get_jid_from_name(depname)
            if hashed_dep in self.jobs:
                job_dep_list = [self.jobs[hashed_dep]]
            elif depname in self.dep_rules:
                job_dep_list = self.dep_rules[depname]
            else:
                raise OrchestratorException.UndefDependencyError(depname)

            for job_dep in job_dep_list:
                if job_dep.name in seen_deps:
                    raise OrchestratorException.CircularDependencyError(str(seen_deps))

                # without copying the chain, resolution of siblings deps will alter
                # the same list --> a single dep may appear multiple time and raise
                # a false CiprcularDep
                # solution: resolve subdep path in their own chain :)
                self.resolve_single_job_deps(job_dep, list(seen_deps))
                job.resolve_a_dep(depname, job_dep)

    def _transpose_dep_graph(self) -> None:
        for _, job in self.jobs.items():
            job.transpose_deps()

    def filter_tags(self) -> None:
        self._transpose_dep_graph()
        change: bool = True
        while change:
            change = False
            for jid, job in self.jobs.items():
                if not job.should_run():
                    io.console.debug(f"Filtering test: {job.name}")
                    job.remove_test_from_deps()
                    self.jobs.pop(jid)
                    self._count["total"] -= 1
                    change = True

    def get_leftjob_count(self) -> int:
        """Return the number of jobs remaining to be executed.

        :return: a number of jobs
        :rtype: int
        """
        return self._count["total"] - self._count["executed"]

    def publish_job(
        self, job: Test, publish_args: tuple[int, float, str, TestState] | None = None
    ) -> None:
        if publish_args is not None:
            job.save_final_result(
                publish_args[0], publish_args[1], publish_args[2], publish_args[3]
            )

        if self._comman:
            self._comman.send(job)
        self._count["executed"] += 1
        if job.state not in self._count:
            self._count[str(job.state)] = 0
        self._count[str(job.state)] += 1
        assert self._publisher is not None
        self._publisher.save(job)

    def prune_all_jobs_as_non_runnable(self) -> None:
        for _, job in self.jobs.items():
            self.publish_failed_to_run_job(job, Test.DISCARDED_STR, TestState.ERR_OTHER)

    def create_subset(self, resources_tracker: ResourceTracker) -> Set | None:
        """Extract one or more jobs, ready to be run.

        :param resources_tracker: job resource tracker.
        :type resources_tracker: list[int]
        :return: A set of jobs
        :rtype: :class:`Set`
        """
        the_set = None
        self._plugin.invoke_plugins(Plugin.Step.SCHED_SET_BEFORE)

        if self._plugin.has_enabled_step(Plugin.Step.SCHED_SET_EVAL):
            the_set = self._plugin.invoke_plugins(
                Plugin.Step.SCHED_SET_EVAL,
                jobman=self,
                max_job_limit=int(self._count["total"] / self._concurrent_level),
            )
        else:
            the_set = self.__default_create_subset(resources_tracker)

        self._plugin.invoke_plugins(Plugin.Step.SCHED_SET_AFTER)
        return the_set

    def __get_next_job(self) -> Test | None:
        if len(self.jobs) <= 0:
            return None
        jid, job = sorted(
            self.jobs.items(), key=lambda entry: entry[1].get_nb_nodes(), reverse=True
        )[0]
        assert job is not None
        self.jobs.pop(jid)
        return job

    def __default_create_subset(self, resources_tracker: ResourceTracker) -> Set | None:
        scheduled_set = None

        user_sched_job = self._plugin.has_enabled_step(Plugin.Step.SCHED_JOB_EVAL)

        to_resched_jobs = []

        while (job := self.__get_next_job()) is not None:
            # test not ready to be run
            if job.state != TestState.WAITING:
                continue

            # if the job has pending dependency,
            # schedule the pending dependency instead of the job itself.
            if not job.has_completed_deps():
                to_resched_jobs.append(job)
                # pick up a dep
                dep_job = job.first_incomplete_dep()
                while dep_job and not dep_job.has_completed_deps():
                    dep_job = dep_job.first_incomplete_dep()
                if dep_job:
                    job = dep_job
                else:
                    # if the dep is already being executed
                    continue

            # from here, it can be the original job or one of its
            # dep tree. But we are sure this job can be processed
            if job.has_failed_dep():
                # Cannot be scheduled for dep purposes
                # push it to publisher
                self.publish_failed_to_run_job(job, Test.NOSTART_STR, TestState.ERR_DEP)
                # Attempt to find another job to schedule
                continue

            # Reached IF Job hasn't be run yet
            # Job has completed its dep scheme
            # all deps are successful
            # => SCHEDULE
            if user_sched_job:
                pick_job = self._plugin.invoke_plugins(
                    Plugin.Step.SCHED_JOB_EVAL, job=job, set=scheduled_set
                )
            else:
                io.console.sched_debug(f"Alloc pool (ALLOC TRY): {job.needed_resources}")
                res = resources_tracker.alloc(job.needed_resources)
                pick_job = res > 0
                if pick_job:
                    io.console.sched_debug(f"Alloc pool (ALLOC RES) {res}: {resources_tracker}")
                    job.alloc_tracking = res

            if job.state != TestState.IN_PROGRESS and pick_job:
                job.pick()
                if scheduled_set is None:
                    scheduled_set = Set(execmode=Set.ExecMode.LOCAL)
                scheduled_set.add(job)
                # Schedule set should only be of size one to avoid
                # issue with multiples runner scheduling as multiples
                # jobs in the same set cannot be scheduled at the same time.
                break

            to_resched_jobs.append(job)
            break

        # readd jobs that can't run but should be rescheduled
        for j in to_resched_jobs:
            self.__add_job(j)

        return scheduled_set

    def publish_failed_to_run_job(self, job: Test, out: str, state: TestState) -> None:
        publish_job_args = (-1, 0.0, out, state)
        self.publish_job(job, publish_args=publish_job_args)
        job.display()

    def merge_subset(self, subset: Set) -> None:
        """After completion, process the Set to publish test results.

        :param set: the set handling jobs during the scheduling.
        :type set: :class:`Set`
        """
        for job in subset.content:
            assert job.state == TestState.EXECUTED

            job.extract_metrics()
            job.save_artifacts()
            job.evaluate()
            self.publish_job(job, publish_args=None)
            job.display()
