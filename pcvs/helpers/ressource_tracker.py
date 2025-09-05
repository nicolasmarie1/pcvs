from typing import Never


class RessourceTracker:

    alloc_tracking_counter: int = 1

    def __init__(self, dims_values: list[int]):
        self.dim = len(dims_values)
        if self.dim == 0:
            self.ressource = 0
        else:
            self.ressources = []
            for _ in range(dims_values[0]):
                self.ressources.append(RessourceTracker(dims_values[1:]))

    def alloc(self, allocation: list[int]) -> int:
        alloc_dim = len(allocation)
        if alloc_dim > self.dim:
            return 0
        tracking_number = RessourceTracker.alloc_tracking_counter
        if self.do_alloc(allocation, tracking_number):
            RessourceTracker.alloc_tracking_counter += 1
            return tracking_number
        return 0

    def do_alloc(self, allocation: list[int], alloc_tracking_id: int) -> bool:
        alloc_dim = len(allocation)
        if alloc_dim < self.dim:
            for ressource in self.ressources:
                if ressource.do_alloc(allocation, alloc_tracking_id):
                    return True
            return False
        if alloc_dim == 0 and self.dim == 0:
            if self.ressource == 0:
                self.ressource = alloc_tracking_id
                return True
            return False
        if alloc_dim == self.dim:
            alloc_ressources = allocation[0]
            count_ressources = 0
            for ressource in self.ressources:
                if ressource.do_alloc(allocation[1:], alloc_tracking_id):
                    count_ressources += 1
                if count_ressources == alloc_ressources:
                    return True
            for ressource in self.ressources:
                ressource.free(alloc_tracking_id)
            return False
        Never.assert_never(allocation)
        return False

    def free(self, alloc_tracking_id: int):
        if self.dim == 0:
            if self.ressource == alloc_tracking_id:
                self.ressource = 0
        else:
            for ressource in self.ressources:
                ressource.free(alloc_tracking_id)

    def __repr__(self):
        if self.dim == 0:
            return str(self.ressource)
        return repr(self.ressources)
