from pcvs.plugins import Plugin


class MPIPlugin(Plugin):
    step = Plugin.Step.TEST_EVAL

    def run(self, *args, **kwargs):  # type: ignore
        """Return True if the combination should be used."""
        hardware_conf = kwargs["config"]["machine"]
        nb_nodes = hardware_conf.get("nodes", 1)
        nb_cores = hardware_conf.get("cores_per_node", 1)

        comb = kwargs["combination"]
        n_mpi = comb.get("n_mpi", 1)
        # n_omp = comb.get('n_omp', 1)
        n_node = comb.get("n_node", 1)
        n_core = comb.get("n_core", nb_cores)

        # more nodes that available in the partition.
        if n_node > nb_nodes:
            return False
        # more mpi tasks that available cpu cores.
        if n_mpi > n_node * min(nb_cores, n_core):
            return False
        return True
