import os
import pprint
from pathlib import Path
from typing import Iterable

from textual import on
from textual.app import App
from textual.binding import Binding
from textual.containers import Container
from textual.containers import Grid
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Button
from textual.widgets import DataTable
from textual.widgets import DirectoryTree
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import Input
from textual.widgets import LoadingIndicator
from textual.widgets import OptionList
from textual.widgets import RichLog
from textual.widgets import Static
from textual.widgets.option_list import Option

from pcvs import NAME_BUILDIR
from pcvs.helpers.utils import check_is_build_or_archive
from pcvs.ui.textual.report.model import ReportModel


class ActiveSessionList(Widget):
    items = reactive(OptionList())
    selected = None

    def __init__(self) -> None:
        """TODO."""
        self.item_list = []
        super().__init__()

    def compose(self) -> Iterable:
        """TODO."""
        self.init_list()
        yield Static("Loaded Sessions:")
        yield self.items
        yield Horizontal(
            Button(label="Done", variant="primary", id="session-pick-done"),
            Button(label="Cancel", variant="error", id="session-pick-cancel"),
        )

    def init_list(self) -> None:
        """TODO."""
        item_names = self.app.model.session_prefixes
        active = self.app.model.active.prefix
        assert active in item_names

        for name in item_names:
            self.item_list.append(Option(name))

        ActiveSessionList.items = OptionList(*self.item_list)

    @on(OptionList.OptionSelected)
    def select_line(self, event: OptionList.OptionSelected) -> None:
        """TODO."""
        self.selected = event.option.prompt

    def add(self, path: str) -> None:
        """TODO."""
        if path not in self.item_list:
            self.item_list.append(path)
            self.app.query_one(ActiveSessionList).items.add_option(item=path)


class FileBrowser(Widget):
    """TODO."""

    BINDINGS = [("q", "pop_screen", "Back")]
    last_select = None
    log = reactive(Static(id="error-log"))

    class CustomDirectoryTree(DirectoryTree):

        def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
            return [
                path for path in paths if check_is_build_or_archive(path) or os.path.isdir(path)
            ]

    def compose(self) -> Iterable:
        """TODO."""
        yield Static("File Browser:")
        yield self.CustomDirectoryTree(os.getcwd(), id="filepicker")
        yield Static("Direct path:")
        yield Input(placeholder="Valid PCVS prefix")
        yield Button(label="Add", variant="primary", id="add-session")
        yield self.log

    @on(DirectoryTree.FileSelected)
    def on_selected_line(self, event: DirectoryTree.FileSelected) -> None:
        event.stop()
        FileBrowser.last_select = event.path


class SessionPickScreen(ModalScreen):

    def compose(self) -> Iterable[Grid]:
        """TODO."""
        yield Grid(ActiveSessionList(), FileBrowser(), id="session-list-screen")

    class SwitchAnotherSession(Message):
        pass

    @on(Button.Pressed, "#session-pick-cancel")
    def pop_screen(self, event: Button.Pressed) -> None:  # pylint: disable=unused-argument
        """TODO."""
        self.app.pop_screen()

    @on(Button.Pressed, "#session-pick-done")
    def set_active_session(self, event: Button.Pressed) -> None:  # pylint: disable=unused-argument
        """TODO."""
        selected_row = self.query_one(ActiveSessionList).selected
        self.app.model.set_active(selected_row)
        self.post_message(SessionPickScreen.SwitchAnotherSession())
        self.app.pop_screen()

    @on(Button.Pressed, "#add-session")
    def add_from_file_browser(
        self, event: Button.Pressed  # pylint: disable=unused-argument
    ) -> None:
        """TODO."""
        if self.query_one(Input).value:
            path = os.path.abspath(os.path.expanduser(self.query_one(Input).value))
        else:
            path = FileBrowser.last_select
        if path is None:
            return
        path = str(path)
        if not check_is_build_or_archive(path):
            self.query_one(FileBrowser).log.update("{} is not a valid PCVS prefix".format(path))
            return
        else:
            self.query_one(FileBrowser).log.update("")

        sid = self.app.model.add_session(path)
        self.app.model.set_active(sid)
        self.app.query_one(ActiveSessionList).add(path)


class JobListViewer(Widget):
    name_colkey = None
    jobgroup = {}
    table = reactive(DataTable())
    BINDINGS = [
        Binding("k", "cursor_up", "Cursor up", show=False),
        Binding("j", "cursor_down", "Cursor down", show=False),
    ]

    def compose(self) -> Iterable[Grid]:
        """TODO."""
        self.table.focus()
        self.table.zebra_stripes = True
        self.table.cursor_type = "row"
        self.name_colkey, _, _ = self.table.add_columns("Name", "Status", "Time (s)")
        self.update_table()

        yield Grid(self.table)

    def update_table(self) -> None:
        """TODO."""
        self.table.clear()
        for _, jobs in self.app.model.single_session_status(self.app.model.active_id).items():
            for jobid in jobs:
                obj = self.app.model.single_session_map_id(self.app.model.active_id, jobid)

                label, color, icon = obj.get_state_fancy()

                self.table.add_row(obj.name, f"[{color}]{icon} {label}[/{color}]", obj.time)
                self.jobgroup[obj.name] = obj
        self.table.sort(self.name_colkey)

    def action_cursor_up(self) -> None:
        """Scroll up jobs list."""
        self.table.action_cursor_up()

    def action_cursor_down(self) -> None:
        """Scroll down jobs list."""
        self.table.action_cursor_down()


class SingleJobViewer(Widget):
    log = reactive(RichLog(wrap=True))
    cmd = reactive(Static())

    def compose(self) -> Iterable:
        """TODO."""
        yield self.cmd
        yield self.log

    def watch_log(self, old: RichLog, new: RichLog) -> None:  # pylint: disable=unused-argument
        """TODO."""
        self.log = new

    def watch_cmd(self, old: Static, new: Static) -> None:  # pylint: disable=unused-argument
        """TODO."""
        self.cmd = new


class MainScreen(Screen):

    def compose(self) -> Iterable:
        """TODO."""
        # with TabbedContent():
        #    with TabPane("main", id="main"):
        # with TabPane("main2", id="main2"):
        yield Header()
        yield JobListViewer()
        yield SingleJobViewer()
        yield Footer()

    @on(DataTable.RowSelected)
    def selected_row(self, event: DataTable.RowSelected) -> None:
        """TODO."""
        name_colkey = self.query_one(JobListViewer).name_colkey
        jobname = self.query_one(DataTable).get_cell(event.row_key, name_colkey)

        obj = self.query_one(JobListViewer).jobgroup[jobname]
        data = "** No Output **" if not obj.output else obj.output

        self.query_one(SingleJobViewer).cmd.update(obj.command)
        logger = self.query_one(SingleJobViewer).log
        logger.clear()
        logger.write(data)


class ExitConfirmScreen(ModalScreen):
    """Screen asking for confirmation before exit."""

    def compose(self) -> Iterable[Grid]:
        """TODO."""
        yield Grid(
            Static("Are you sure you want to quit?", id="question"),
            Button("Quit", variant="error", id="quit"),
            Button("Cancel", variant="primary", id="cancel"),
            id="dialog",
        )

    @on(Button.Pressed)
    def press_exit_screen_button(self, event: Button.Pressed) -> None:
        """TODO."""
        if event.button.id == "quit":
            self.app.exit()
        else:
            self.app.pop_screen()


class PleaseWaitScreen(ModalScreen):

    def compose(self) -> Iterable:
        """TODO."""
        yield Static("Please Wait...")
        yield LoadingIndicator()


class SessionInfoScreen(ModalScreen):

    def compose(self) -> Iterable[Container]:
        """TODO."""
        # display = {
        #     "datetime": Static("Date of run:"),
        #     "pf_name": Static("Profile:"),
        # }
        config = self.app.model.active.config
        infolog = RichLog()

        infolog.write(pprint.pformat(config))

        yield Container(
            Horizontal(
                Static("File Path:"),
                Static(self.app.model.active.prefix),
            ),
            Static("Configuration:"),
            infolog,
            Button("Done"),
            id="session-infos",
        )

    @on(Button.Pressed)
    def quit_infos(self, event: Button.Pressed) -> None:  # pylint: disable=unused-argument
        """TODO."""
        self.app.pop_screen()


class ReportApplication(App):
    """
    Main Application handler.
    """

    TITLE = "PCVS Job Result Viewer"
    SCREENS = {
        "main": MainScreen,
        "exit": ExitConfirmScreen,
        "wait": PleaseWaitScreen,
        "session_list": SessionPickScreen,
        "session_infos": SessionInfoScreen,
    }
    BINDINGS = [
        ("q", 'push_screen("exit")', "Exit"),
        ("o", 'push_screen("session_list")', "Open"),
        ("t", "toggle_dark", "Dark mode"),
        ("c", "push_screen('session_infos')", "Infos"),
    ]
    CSS_PATH = "main.css"

    @on(SessionPickScreen.SwitchAnotherSession)
    def switch_session(
        self, event: SessionPickScreen.SwitchAnotherSession  # pylint: disable=unused-argument
    ) -> None:
        """
        Coming back from picking a session, refresh the table.

        :param event: not significant here
        """
        self.app.query_one(JobListViewer).update_table()

    def on_mount(self) -> None:
        """
        First screen loaded.
        """
        self.push_screen("main")

    def __init__(self, model: ReportModel | None = None):
        """
        Init the application with a model.

        Currently, a model is a derived class from BuildDirectoryManager

        :param model: the model used to access resources
        :type model: ReportModel
        """
        if model is None:
            path = os.path.abspath(os.path.join(os.getcwd(), NAME_BUILDIR))
            model = ReportModel([path])
        self.model: ReportModel = model
        super().__init__()


def start_app(p: list[str]) -> int:  # pylint: disable=unused-argument
    """
    Handle to start a new Textual application.

    :param p: profile, defaults to None
    :type p: list of config files, optional
    :return: A return code from Textual Application
    :rtype: int
    """
    app: ReportApplication = ReportApplication(ReportModel(p))
    res = app.run()
    assert isinstance(res, int)
    return res
