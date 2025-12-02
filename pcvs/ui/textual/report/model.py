from pcvs.backend.report import Report
from pcvs.orchestration.publishers import BuildDirectoryManager


class ReportModel(Report):

    def __init__(self, build_paths: list[str]):

        assert isinstance(build_paths, list)
        super().__init__()
        active_hdl: BuildDirectoryManager | None = None
        for path in build_paths:
            hdl = self.add_session(path)
            if not active_hdl:
                active_hdl = hdl
        assert active_hdl is not None
        self.active_hdl: BuildDirectoryManager = hdl

    @property
    def active(self) -> BuildDirectoryManager:
        return self.active_hdl

    @property
    def active_id(self) -> str:
        return self.active_hdl.sid

    @property
    def session_prefixes(self) -> list[str]:
        return [x["path"] for x in self.session_infos()]

    def set_active(self, hdl: BuildDirectoryManager | None) -> None:
        if hdl is None:
            return
        if isinstance(hdl, str):
            for v in self._sessions.values():
                if hdl == v.prefix:
                    hdl = v
                    break
        self.active_hdl = hdl
