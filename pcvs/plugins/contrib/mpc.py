from pcvs import io
from pcvs.plugins import Plugin


class MpcDefaultPlugin(Plugin):
    """
    MPC validation plugin
    """
    step = Plugin.Step.TEST_EVAL

    def run(self, *args, **kwargs):
        # this dict maps keys (it name) with values (it value)
        # returns True if the combination should be used
        config = kwargs['config']
        nb_nodes = config['machine'].get('nodes', 1)
        nb_cores = config['machine'].get('cores_per_node', 1)

        comb = kwargs['combination']
        n_node = comb.get('n_node', 1)      # N
        n_proc = comb.get('n_proc', None)   # p
        n_mpi = comb.get('n_mpi', None)     # n
        n_core = comb.get('n_core', None)   # c
        n_omp = comb.get('n_omp', None)     # omp
        net = comb.get('net', None)
        # sched = comb.get('sched', None)

        # if neither n_mpi and n_proc are specify -> n_node
        if n_mpi is None and n_proc is None:
            n_mpi, n_proc = n_node, n_node
        else:
            # if n_mpi is not specify -> n_proc
            if n_mpi is None:
                n_mpi = n_proc
            # if n_proc us not specify -> n_mpi
            if n_proc is None:
                n_proc = n_mpi

        comb = (f"Combination: nodes:{n_node}, processes:{n_proc}, "
                f"mpi:{n_mpi}, cpu:{n_core}, omp:{n_omp}: ")
        if n_node > nb_nodes:
            io.console.debug(f"{comb}Ask for more nodes that present in the "
                             f"current partition\t{n_node} > {nb_nodes}")
            return False
        if n_node > n_proc:
            io.console.debug(f"{comb}Ask for more nodes that processes"
                             f"\t{n_node} > {n_proc}")
            return False
        if n_proc > n_mpi:
            io.console.debug(f"{comb}Ask for more processes than mpi tasks"
                             f"\t{n_proc} > {n_mpi}")
            return False
        nb_cores_total = nb_cores * n_node
        if n_proc > nb_cores_total:
            io.console.debug(f"{comb}Ask for more processes than available "
                             f"cpus per nodes\t{n_proc} > {nb_cores_total}")
            return False
        nb_core_per_proc = (nb_cores * n_node) // n_proc
        if n_core is not None and n_core > 1 and n_core > nb_core_per_proc:
            io.console.debug(f"{comb}Ask for more cpus per processes than "
                             f"available cpus on allocated nodes"
                             f"\t{n_core} > {nb_core_per_proc}")
            return False
        if net is not None and n_node > 1 and net == "shmem":
            io.console.debug(f"{comb}Ask for multi nodes jobs while using "
                             f"shared memory\t{n_node} > 1 and net == {net}")
            return False

        io.console.debug(f"{comb}OK")
        return True
