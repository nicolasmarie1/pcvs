from typeguard import typechecked


@typechecked
class ResourceTracker:

    alloc_tracking_counter: int = 1

    def __init__(self, dims_values: list[int]):
        self.dim = len(dims_values)
        if self.dim == 0:
            self.resource = 0
        else:
            self.resources = []
            for _ in range(dims_values[0]):
                self.resources.append(ResourceTracker(dims_values[1:]))

    def alloc(self, allocation: list[int]) -> int:
        alloc_dim = len(allocation)
        if alloc_dim > self.dim:
            return 0
        tracking_number = ResourceTracker.alloc_tracking_counter
        if self.do_alloc(allocation, tracking_number):
            ResourceTracker.alloc_tracking_counter += 1
            return tracking_number
        return 0

    def do_alloc(self, allocation: list[int], alloc_tracking_id: int) -> bool:
        alloc_dim = len(allocation)
        if alloc_dim < self.dim:
            for resource in self.resources:
                if resource.do_alloc(allocation, alloc_tracking_id):
                    return True
            return False
        if alloc_dim == 0 and self.dim == 0:
            if self.resource == 0:
                self.resource = alloc_tracking_id
                return True
            return False
        if alloc_dim == self.dim:
            alloc_resources = allocation[0]
            assert alloc_resources is not None
            count_resources = 0
            for resource in self.resources:
                if resource.do_alloc(allocation[1:], alloc_tracking_id):
                    count_resources += 1
                if count_resources == alloc_resources:
                    return True
            for resource in self.resources:
                resource.free(alloc_tracking_id)
            return False
        assert False

    def free(self, alloc_tracking_id: int) -> None:
        if self.dim == 0:
            if self.resource == alloc_tracking_id:
                self.resource = 0
        else:
            for resource in self.resources:
                resource.free(alloc_tracking_id)

    def __repr__(self) -> str:
        if self.dim == 0:
            return str(self.resource)
        return repr(self.resources)
