from pcvs import io
from pcvs.helpers.exceptions import OrchestratorException
from pcvs.helpers.resource_tracker import ResourceTracker
from pcvs.helpers.system import GlobalConfig
from pcvs.orchestration.set import Set
from pcvs.plugins import Plugin
from pcvs.testing.test import Test


class Manager:
    """Gather and manipulate Jobs under a hiararchical architecture.

    A Manager is in charge of carrying jobs during the scheduling. Jobs are
    divided hierarchicaly (basically, depending on the number of resource
    requested to be run). To extract jobs to be scheduled, a Manager will create
    Set()s. Once completed Sets are merged to the Manager before publishing the
    results.

    :ivar dims: hierarchical dict storing jobs
    :type dims: dict
    :ivar _max_size: max number of resources allowed by the profile
    :type _max_size: int
    :ivar _publisher: the Formatter object, publishing results into files
    :type _publisher: :class:`ResultFileManager`
    :ivar _count: dict gathering various counters (total, executed...)
    :type _count: dict
    """

    jobs = {}
    dep_rules = {}

    def __init__(self, max_nodes=0, publisher=None):
        """constructor method.

        :param max_size: max number of resource allowed to schedule.
        :type max_size: int
        :param builder: Not used yet
        :type builder: None
        :param publisher: requested publisher by the orchestrator
        :type publisher: :class:`ResultFileManager`
        """
        self._comman = GlobalConfig.root.get_internal("comman")
        self._plugin = GlobalConfig.root.get_internal("pColl")
        self._concurrent_level = GlobalConfig.root["machine"].get("concurrent_run", 1)

        self._max_nodes = max_nodes
        self._dims = {n: [] for n in range(1, self._max_nodes + 1)}
        self._publisher = publisher
        self._count = {"total": 0, "executed": 0}

    def get_dim(self, dim):
        """Get the list of jobs satisfying the given dimension.

        :param dim: the target dim
        :type dim: int
        :return: the list of jobs for this dimension, empty if dim is invalid
        :rtype: list
        """
        if dim not in self._dims:
            return []
        return self._dims[dim]

    @property
    def nb_max_nodes(self):
        """Get max number of nodes.

        :return: the max nb nodes
        :rtype: int
        """
        return self._max_nodes

    def __add_job(self, job):
        """Store a new job to the job Queue.

        :param job: The job to append
        :type job: :class:`Test`
        """
        test_nodes_nb = min(self._max_nodes, job.get_nb_nodes())

        self._dims[test_nodes_nb].append(job)

    def add_job(self, job):
        """Store a new job to the Job Queue, the Manager table,
            save the test dependency rules and count it.

        :param job: The job to append
        :type job: :class:`Test`
        """
        self.__add_job(job)

        # if test is not know yet, add + increment
        if job.jid not in self.jobs:
            self.jobs[job.jid] = job
            self._count["total"] += 1
            self.save_dependency_rule(job.basename, job)

    def save_dependency_rule(self, pattern, jobs):
        assert isinstance(pattern, str)

        if not isinstance(jobs, list):
            jobs = [jobs]

        self.dep_rules.setdefault(pattern, [])
        self.dep_rules[pattern] += jobs

    def get_count(self, tag="total"):
        """Access to a particular counter.

        :param tag: a specific counter to target, defaults to "total"
        :type tag: str
        :return: a count
        :rtype: int
        """
        return self._count[tag] if tag in self._count else 0

    def resolve_deps(self):
        """Resolve the whole dependency graph.

        This function is meant to be called once and browse every single tests
        to resolve dep names to their real associated object.
        """
        for joblist in self._dims.values():
            for job in joblist:
                self.resolve_single_job_deps(job, [])

    def print_dep_graph(self, outfile=None):
        s = ["digraph D {"]
        for joblist in self._dims.values():
            for job in joblist:
                for d in job.get_dep_graph().keys():
                    s.append('"{}"->"{}";'.format(job.name, d))
        s.append("}")

        if not outfile:
            print("\n".join(s))
        else:
            with open(outfile, "w") as fh:
                fh.write("\n".join(s))

    def resolve_single_job_deps(self, job, chain):
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
        chain.append(job.name)
        for depname in job.job_depnames:

            hashed_dep = Test.get_jid_from_name(depname)
            if hashed_dep in self.jobs:
                job_dep_list = [self.jobs[hashed_dep]]
            elif depname in self.dep_rules:
                job_dep_list = self.dep_rules[depname]
            else:
                raise OrchestratorException.UndefDependencyError(depname)

            for job_dep in job_dep_list:
                if job_dep.name in chain:
                    raise OrchestratorException.CircularDependencyError(chain)

                # without copying the chain, resolution of siblings deps will alter
                # the same list --> a single dep may appear multiple time and raise
                # a false CiprcularDep
                # solution: resolve subdep path in their own chain :)
                self.resolve_single_job_deps(job_dep, list(chain))
                job.resolve_a_dep(depname, job_dep)

    def _transpose_dep_graph(self):
        for joblist in self._dims.values():
            for job in joblist:
                job.transpose_deps()

    def filter_tags(self):
        self._transpose_dep_graph()
        change: bool = True
        while change:
            change = False
            for joblist in self._dims.values():
                for job in joblist:
                    if job.filter_run():
                        job.remove_test_from_deps()
                        joblist.remove(job)
                        self._count["total"] -= 1
                        change = True

    def get_leftjob_count(self):
        """Return the number of jobs remaining to be executed.

        :return: a number of jobs
        :rtype: int
        """
        return self._count["total"] - self._count["executed"]

    def publish_job(self, job, publish_args=None):
        if publish_args:
            job.save_final_result(**publish_args)

        if self._comman:
            self._comman.send(job)
        self._count["executed"] += 1
        if job.state not in self._count:
            self._count[job.state] = 0
        self._count[job.state] += 1
        self._publisher.save(job)

    def prune_non_runnable_jobs(self):
        for k in sorted(self._dims.keys(), reverse=True):
            if len(self._dims[k]) <= 0:
                continue
            removed_jobs = []
            for job in self._dims[k]:
                if job.pick_count() > Test.SCHED_MAX_ATTEMPTS:
                    self.publish_failed_to_run_job(job, Test.MAXATTEMPTS_STR, Test.State.ERR_OTHER)
                    removed_jobs.append(job)
            for elt in removed_jobs:
                self._dims[k].remove(elt)
            return len(removed_jobs) > 0

    def create_subset(self, resources_tracker: ResourceTracker):
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

    def __get_next_job(self) -> Test:
        for k in sorted(self._dims.keys(), reverse=True):
            job: Test = None
            while len(self._dims[k]) > 0:
                job = self._dims[k].pop(0)
                assert job is not None
                return job
        return None

    def __default_create_subset(self, resources_tracker: ResourceTracker):
        scheduled_set = None

        user_sched_job = self._plugin.has_enabled_step(Plugin.Step.SCHED_JOB_EVAL)

        while (job := self.__get_next_job()) is not None:
            if job.been_executed() or job.state == Test.State.IN_PROGRESS:
                continue

            # if the job has pending dependency,
            # schedule the pending dependency instead of the job itself.
            if not job.has_completed_deps():
                self.__add_job(job)
                # pick up a dep
                dep_job = job.first_incomplete_dep()
                while dep_job and not dep_job.has_completed_deps():
                    dep_job = dep_job.first_incomplete_dep()
                if dep_job:
                    job = dep_job
                else:
                    # possible due to race condition, ignore
                    continue

            # from here, it can be the original job or one of its
            # dep tree. But we are sure this job can be processed
            if job.has_failed_dep():
                # Cannot be scheduled for dep purposes
                # push it to publisher
                self.publish_failed_to_run_job(job, Test.NOSTART_STR, Test.State.ERR_DEP)
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

            if job.state != Test.State.IN_PROGRESS and pick_job:
                job.pick()
                if scheduled_set is None:
                    scheduled_set = Set(execmode=Set.ExecMode.LOCAL)
                scheduled_set.add(job)
                # Schedule set should only be of size one to avoid
                # issue with multiples runner scheduling as multiples
                # jobs in the same set cannot be scheduled at the same time.
                break

            if job.is_never_picked():
                self.publish_failed_to_run_job(job, Test.MAXATTEMPTS_STR, Test.State.ERR_OTHER)
            else:
                self.__add_job(job)
                break

        return scheduled_set

    def publish_failed_to_run_job(self, job, out, state):
        publish_job_args = {"rc": -1, "time": 0.0, "out": out, "state": state}
        self.publish_job(job, publish_args=publish_job_args)
        job.display()

    def merge_subset(self, subset):
        """After completion, process the Set to publish test results.

        :param set: the set handling jobs during the scheduling.
        :type set: :class:`Set`
        """
        for job in subset.content:
            if job.been_executed():
                job.extract_metrics()
                job.save_artifacts()
                job.evaluate()
                self.publish_job(job, publish_args=None)
                job.display()
            else:

                if job.not_picked():
                    self.publish_failed_to_run_job(job, Test.MAXATTEMPTS_STR, Test.State.ERR_OTHER)
                else:
                    self.add_job(job)
