from pcvs.plugins import Plugin


class OmpPlugin(Plugin):
    step = Plugin.Step.TEST_EVAL

    def run(self, *args, **kwargs):
        """Return True if the combination should be used."""
        hardware_conf = kwargs["config"]["machine"]
        # nb_nodes = hardware_conf.get("nodes", 1)
        nb_cores = hardware_conf.get("cores_per_node", 1)

        comb = kwargs["combination"]
        # n_mpi = comb.get("n_mpi", 1)
        n_omp = comb.get("n_omp", 1)
        # n_node = comb.get("n_node", 1)
        n_core = comb.get("n_core", nb_cores)

        # more omp threads than available cpu cores.
        if n_omp > min(n_core, nb_cores):
            return False
        return True
