from pcvs.plugins import Plugin


class MPIOmpPlugin(Plugin):
    step = Plugin.Step.TEST_EVAL

    def run(self, *args, **kwargs):
        # returns True if the combination should be used
        config = kwargs["config"]
        nb_nodes = config["machine"].get("nodes", 1)
        nb_cores = config["machine"].get("cores_per_node", 1)

        comb = kwargs["combination"]
        n_mpi = comb.get("n_mpi", 1)
        n_omp = comb.get("n_omp", 1)
        n_node = comb.get("n_node", 1)

        if n_mpi * n_omp > n_node * nb_cores:
            return False
        if n_node > nb_nodes:
            return False
        if n_omp > nb_cores:
            return False
        return True
