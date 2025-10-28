import enum
import functools
import logging
import os
import shutil
import sys
from datetime import datetime
from importlib.metadata import version
from typing import Callable
from typing import Dict
from typing import Iterable
from typing import Optional

import click
from rich import box
from rich.console import Console
from rich.live import Live
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import BarColumn
from rich.progress import Progress
from rich.progress import SpinnerColumn
from rich.progress import TextColumn
from rich.progress import TimeElapsedColumn
from rich.progress import track
from rich.style import Style
from rich.table import Table
from rich.theme import Theme

import pcvs


class SpecialChar:
    """
    Class mapping special char display.

    Enabled or disabled according to utf support.
    """

    copy = "\u00a9"
    item = "\u27e2"
    sec = "\u2756"
    hdr = "\u23bc"
    star = "\u2605"
    fail = "\u2718"
    succ = "\u2714"
    none = "\u2205"
    git = "\u237f"
    time = "\U0000231a"
    sep_v = " \u237f "
    sep_h = "\u23bc"

    def __init__(self, utf_support: Optional[bool] = True) -> None:
        """
        Initialize a new char handler depending on utf support

        :param utf_support: support for utf encoding, defaults to True
        :type utf_support: bool, optional
        """
        if not utf_support:
            self.copy = "(c)"
            self.item = "*"
            self.sec = "#"
            self.hdr = "="
            self.star = "*"
            self.fail = "X"
            self.succ = "V"
            self.none = "-"
            self.git = "(git)"
            self.time = "(time)"
            self.sep_v = " | "
            self.sep_h = "-"


class Verbosity(enum.IntEnum):
    """
    Enum to map a verbosity level to a more
    convenient label.

    * COMPACT: compact way, jobs are displayed packed per input YAML file.
    * DETAILED: each job will output result on a one-line manner
    * INFO: DETAILED & INFO messages will be logged
    * DEBUG: DETAILED & INFO & DEBUG messages will be logged
    """

    COMPACT = 0
    DETAILED = 1
    INFO = 2
    DEBUG = 3
    NB_LEVELS = enum.auto()

    def __str__(self) -> str:
        """
        Convert object to human-readable string

        :return: a verbosity as printable string
        :rtype: str
        """
        return self.name


class PCVSConsole:
    """
    Main interface to print information to users.

    Any output from the application should be handled by this Console.
    """

    # Should match ALL_STATES in pcvs.testing.test.Test
    # Can't import that here as it would create circular dependency
    ALL_STATES = [
        "SUCCESS",
        "FAILURE",
        "ERR_DEP",
        "HARD_TIMEOUT",
        "SOFT_TIMEOUT",
        "ERR_OTHER",
    ]

    def __init__(self, **kwargs) -> None:
        """
        Build a new Console:
        - color: boolean (color support)
        - verbose: boolean (verbose msg mode in log files)
        Any other argument is considered a base class options.

        :param args: any argument to be forwarded to Rich console, as list
        :type args: list
        :param kwargs: any argument to be forwarded to Rich Console as dict
        :type kwargs: dict
        """
        self._progress = None
        self._singletask = None
        self.live = None

        self._color = kwargs.get("color", True)
        self._verbose = Verbosity(min(Verbosity.NB_LEVELS - 1, kwargs.get("verbose", 0)))
        self._debugfile = open(os.path.join(".", pcvs.NAME_DEBUG_FILE), "w", encoding="utf-8")
        self.job_summary_data_table: Dict[str, Dict[str, Dict[str, int]]] = {}
        log_level = "DEBUG" if self._verbose else "INFO"
        # https://rich.readthedocs.io/en/stable/appendix/colors.html#appendix-colors
        theme = Theme(
            {
                "debug": Style(color="white"),
                "info": Style(color="bright_white"),
                "warning": Style(color="yellow", bold=True),
                "danger": Style(color="red", bold=True),
            }
        )
        color_system = "auto" if self._color else None
        self._stdout = Console(color_system=color_system, theme=theme)
        self._stderr = Console(color_system=color_system, theme=theme, stderr=True)
        self._debugconsole = Console(
            color_system=color_system,
            theme=theme,
            file=self._debugfile,
            markup=self._color,
        )

        logging.basicConfig(
            level=log_level,
            format="%(message)s",
            handlers=[
                RichHandler(
                    console=self._debugconsole,
                    omit_repeated_times=False,
                    rich_tracebacks=True,
                    show_level=True,
                    tracebacks_suppress=[click],
                    show_path=True,
                )
            ],
        )
        self._loghdl = logging.getLogger("pcvs")
        self._chars = SpecialChar(utf_support=self._stdout.encoding.startswith("utf"))

        # Activate when needed
        self._sched_debug = False
        self._crit_debug = False

    # log file management

    @property
    def logfile(self):
        """
        Get the path to the logging file.

        :return: the logging file
        :rtype: str
        """
        return os.path.abspath(self._debugfile.name)

    @property
    def outfile(self):
        """
        Get the path where the Console output is logged (disabled by default).

        :return: the file path
        :rtype: str
        """
        return os.path.abspath(self._stdout.file.name)

    def setoutfile(self, file):
        self._stdout.file = file
        self._stderr.file = file

    def __del__(self):
        """Make sure files are closed when stopping PCVS."""
        if self._debugfile:
            self._debugfile.close()
            self._debugfile = None

    def move_debug_file(self, newdir):
        assert os.path.isdir(newdir)
        if self._debugfile:
            shutil.move(self._debugfile.name, os.path.join(newdir, pcvs.NAME_DEBUG_FILE))
        else:
            self.warning("No '{}' file found for this Console".format(pcvs.NAME_DEBUG_FILE))

    # Verbosity

    @property
    def verbose(self):
        """Return the Verbosity level."""
        return self._verbose

    def verb_level(self, level):
        """Return True if Verbosity level is <level> or above."""
        return self._verbose >= level

    @property
    def verb_compact(self):
        """Return True if Verbosity level is COMPACT or above."""
        return self.verb_level(Verbosity.COMPACT)

    @property
    def verb_detailed(self):
        """Return True if Verbosity level is DETAILED or above."""
        return self.verb_level(Verbosity.DETAILED)

    @property
    def verb_info(self):
        """Return True if Verbosity level is INFO or above."""
        return self.verb_level(Verbosity.INFO)

    @property
    def verb_debug(self):
        """Return True if Verbosity level is DEBUG or above."""
        return self.verb_level(Verbosity.DEBUG)

    @verbose.setter
    def verbose(self, v):
        """Set Verbosity level."""
        self._verbose = v

    # Standard printers

    def nodebug(self, fmt, *args, **kwargs):
        """Do nothing, place holder to remove debug statement without deleting lines."""

    def debug(self, fmt, *args, **kwargs):
        """Print & log debug."""
        self._loghdl.debug(fmt, *args, **kwargs)
        if self._verbose >= Verbosity.DEBUG:
            user_fmt = fmt.format(*args, **kwargs) if args or kwargs else fmt
            self._stdout.print(f"[debug]\\[debug]: {user_fmt}[/debug]", soft_wrap=True)

    def info(self, fmt, *args, **kwargs):
        """Print & log info."""
        self._loghdl.info(fmt, *args, **kwargs)
        if self._verbose >= Verbosity.INFO:
            user_fmt = fmt.format(*args, **kwargs) if args or kwargs else fmt
            self._stdout.print(f"[info]\\[info]: {user_fmt}[/info]", soft_wrap=True)

    def warning(self, fmt, *args, **kwargs):
        """Print & log warning."""
        self._loghdl.warning(fmt, *args, **kwargs)
        user_fmt = fmt.format(*args, **kwargs) if args or kwargs else fmt
        self._stderr.print(f"[warning]\\[warning]: {user_fmt}[/warning]", soft_wrap=True)

    def warn(self, fmt, *args, **kwargs):
        """Short for warning."""
        self.warning(fmt, *args, **kwargs)

    def error(self, fmt, *args, **kwargs):
        """Print a log error messages."""
        user_fmt = fmt.format(*args, **kwargs) if args or kwargs else fmt
        self._stderr.print(f"[danger]\\[error]: {user_fmt}[/danger]", soft_wrap=True)
        self._loghdl.error(fmt, *args, **kwargs)

    def critical(self, fmt, *args, **kwargs):
        """Print a log critical error then exit."""
        user_fmt = fmt.format(*args, **kwargs) if args or kwargs else fmt
        self._stderr.print(f"[danger]\\[CRITICAL]: {user_fmt}[/danger]", soft_wrap=True)
        self._loghdl.critical(fmt, *args, **kwargs)
        sys.exit(42)

    def exception(self, e: BaseException):
        """Print exceptions."""
        if self._verbose >= Verbosity.DEBUG:
            self._stderr.print_exception(word_wrap=True, show_locals=True)
        else:
            self._stderr.print_exception(extra_lines=0)
        self._loghdl.exception(e)

    def crit_debug(self, fmt):
        """Print & log debug for pcvs criterions."""
        if self._crit_debug:
            self.debug(f"[CRIT]{fmt}")

    def sched_debug(self, fmt):
        """Print & log debug for pcvs scheduler."""
        if self._sched_debug:
            self.debug(f"[SCHED]{fmt}")

    @property
    def logger(self):
        """Get Logger."""
        return self._loghdl

    # Other printers

    def print(self, fmt=""):
        """Print a line to stdout."""
        self._stdout.print(fmt)
        self._loghdl.info("[PRINT] %s", fmt)

    def print_section(self, txt):
        """Print Section."""
        self._stdout.print("[yellow bold]{} {}[/]".format(self.utf("sec"), txt), soft_wrap=True)
        self._loghdl.info("[DISPLAY] ======= %s ======", txt)

    def print_header(self, txt):
        """Print Header."""
        self._stdout.rule("[green bold]{}[/]".format(txt.upper()))
        self._loghdl.info("[DISPLAY] ------- %s ------", txt)

    def print_item(self, txt, depth=1):
        """Print Item."""
        self._stdout.print(
            "[red bold]{}{}[/] {}".format(" " * (depth * 2), self.utf("item"), txt), soft_wrap=True
        )
        self._loghdl.info("[DISPLAY] * %s", txt)

    def print_box(self, txt, *args, **kwargs):
        """Print a Box."""
        panel_box = Panel.fit(txt, *args, **kwargs)
        self._stdout.print(panel_box)
        self._loghdl.info("[DISPLAY] BOX %s", panel_box)

    # Others

    def _get_display_table(self, include_jobs: bool = False):
        """Get the table to display for live update.

        Include the progress bar, may include the job view table.
        """
        table = Table.grid(expand=True)
        if include_jobs:
            table.add_row(self._get_job_table())
        else:
            # Add spacing
            table.add_row()
        table.add_row(self._progress)
        return table

    def _get_job_table(self) -> Table:
        """Transform the job data table into a job view table."""
        table = Table(expand=True, box=box.SIMPLE)
        table.add_column("Name", justify="left", ratio=10)
        for state in PCVSConsole.ALL_STATES:
            table.add_column(state, justify="center")
        for label, lvalue in self.job_summary_data_table.items():
            for subtree, svalue in lvalue.items():
                if sum(svalue.values()) == svalue.get("SUCCESS", 0):
                    colour = "green"
                elif svalue.get("FAILURE", 0) > 0:
                    colour = "red"
                else:
                    colour = "yellow"
                columns_list = [f"[{colour} bold]{x}" for x in svalue.values()]
                table.add_row(f"[{colour} bold]{label}{subtree}", *columns_list)
        return table

    def _insert_job_table(self, state, test_label, test_subtree):
        """Insert a job in the job data table.

        This job table is display is the one displayed when running
        on low verbosity level or at the end of the run.
        """
        self.job_summary_data_table.setdefault(test_label, {})
        self.job_summary_data_table[test_label].setdefault(
            test_subtree,
            {label: 0 for label in PCVSConsole.ALL_STATES},
        )
        self.job_summary_data_table[test_label][test_subtree][str(state)] += 1

    def print_job(self, status_str, state, tlabel, tsubtree, content=None):
        """Print a Job.

        If Verbosity level is equal or above Verbosity.DETAILED, print each tests.
        Otherwise, print a summary block.
        Optionally print raw test result content.
        """
        # Update Job data table state.
        self._insert_job_table(state, tlabel, tsubtree)
        # Update progress bar state.
        self._progress.advance(self._singletask)
        if self.verb_detailed:
            # Print the test status line.
            self._stdout.print(status_str)
            if content:
                # Print raw test output.
                self._stdout.out(content)
        # Update the table/progressbar display.
        self.live.update(self._get_display_table(not self.verb_detailed))

    def print_job_summary(self):
        """Print the job view table once."""
        self._stdout.print(self._get_job_table())

    def table_container(self, total) -> Live:
        """The main pcvs run progress bar that may include job summary."""
        self._progress = Progress(
            TimeElapsedColumn(),
            "Progress",
            BarColumn(bar_width=None, complete_style="yellow", finished_style="green"),
            TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
            SpinnerColumn(speed=0.5),
            expand=True,
        )
        self._singletask = self._progress.add_task("Progress", total=int(total))
        self.live = Live(self._get_display_table(False), console=self._stdout)
        return self.live

    def create_table(self, title, cols) -> Table:
        """Create and return a rich table."""
        return Table(*cols, title=title)

    def progress_iter(self, it: Iterable, **kwargs) -> Iterable:
        """Print a progress bar using click.

        :param it: iterable on which the progress bar has to iterate
        :type it: Iterable
        :param kwargs: any extra info forwarded to click progress bar handler
        :type kwargs: dict
        :return: a click progress bar (iterable)
        :rtype: Iterable
        """
        return track(
            it,
            transient=True,
            console=self._stdout,
            complete_style="cyan",
            pulse_style="green",
            refresh_per_second=4,
            description="[red]In Progress...[red]",
            **kwargs,
        )

    def utf(self, k) -> str:
        """
        Return the encoding supported by this session for the given key.

        :param k: the key as defined by SpecialChar
        :type k: str
        :return: the associated printable sequence
        :rtype: str
        """
        return getattr(self._chars, k)

    def print_banner(self) -> None:
        """
        Print the PCVS logo fitting with current terminal size
        """

        logo_minimal = [
            r"""[green]{}""".format(self.utf("star") * 19),
            r"""[yellow]     -- PCVS --  """,
            r"""[red]{} CEA {} 2017-{} {}""".format(
                self.utf("star"), self.utf("copy"), datetime.now().year, self.utf("star")
            ),
            r"""[green]{}""".format(self.utf("star") * 19),
        ]

        logo_short = [
            r"""[green  ]     ____    ______  _    __  _____""",
            r"""[green  ]    / __ \  / ____/ | |  / / / ___/""",
            r"""[green  ]   / /_/ / / /      | | / /  \__ \ """,
            r"""[yellow ]  / ____/ / /___    | |/ /  ___/ / """,
            r"""[red    ] /_/      \____/    |___/  /____/  """,
            r"""[red    ]                                   """,
            r"""[default] Parallel Computing -- Validation System""",
            r"""[default] Copyright {} 2017-{} -- CEA""".format(
                self.utf("copy"), datetime.now().year
            ),
            r"""""",
        ]

        logo = [
            r"""[green  ]     ____                   ____     __   ______                            __  _             """,
            r"""[green  ]    / __ \____ __________ _/ / /__  / /  / ____/___  ____ ___  ____  __  __/ /_(_)___  ____ _ """,
            r"""[green  ]   / /_/ / __ `/ ___/ __ `/ / / _ \/ /  / /   / __ \/ __ `__ \/ __ \/ / / / __/ / __ \/ __ `/ """,
            r"""[green  ]  / ____/ /_/ / /  / /_/ / / /  __/ /  / /___/ /_/ / / / / / / /_/ / /_/ / /_/ / / / / /_/ /  """,
            r"""[green  ] /_/    \__,_/_/   \__,_/_/_/\___/_/   \____/\____/_/ /_/ /_/ .___/\__,_/\__/_/_/ /_/\__, /   """,
            r"""[green  ]                                                           /_/                     /____/     """,
            r"""[default]                                            {} ([link=https://pcvs.io]PCVS[/link]) {}""".format(
                self.utf("star"), self.utf("star")
            ),
            r"""[green  ]    _    __      ___     __      __  _                _____            __                    """,
            r"""[green  ]   | |  / /___ _/ (_)___/ /___ _/ /_(_)___  ____     / ___/__  _______/ /____  ____ ___      """,
            r"""[green  ]   | | / / __ `/ / / __  / __ `/ __/ / __ \/ __ \    \__ \/ / / / ___/ __/ _ \/ __ `__ \     """,
            r"""[yellow ]   | |/ / /_/ / / / /_/ / /_/ / /_/ / /_/ / / / /   ___/ / /_/ /__  / /_/  __/ / / / / /     """,
            r"""[red    ]   |___/\__,_/_/_/\__,_/\__,_/\__/_/\____/_/ /_/   /____/\__, /____/\__/\___/_/ /_/ /_/      """,
            r"""[red    ]                                                        /____/                               """,
            r"""[red    ]                                                                                             """,
            r"""[default]  Copyright {} 2017-{} Commissariat à l'Énergie Atomique et aux Énergies Alternatives ([link=https://cea.fr]CEA[/link])""".format(
                self.utf("copy"), datetime.now().year
            ),
            r"""[default]                                                                                             """,
            r"""[default]  This program comes with ABSOLUTELY NO WARRANTY;""",
            r"""[default]  This is free software, and you are welcome to redistribute it""",
            r"""[default]  under certain conditions; Please see COPYING for details.""",
            r"""[default]                                                                                             """,
        ]
        banner = logo

        if self._stdout.size.width < 40:
            banner = logo_minimal
        elif self._stdout.size.width < 95:
            banner = logo_short

        self._stdout.print("\n".join(banner))
        pcvs_version = version("pcvs")
        self._stdout.print(f"Parallel Computing Validation System (pcvs) -- version {pcvs_version}")


console = None


def init(color=True, verbose=0, *args, **kwargs):
    """Init the PCVS Console."""
    global console
    console = PCVSConsole(color=color, verbose=verbose, *args, **kwargs)


def detach_console():
    """Detach the PCVS Console."""
    logfile = os.path.join(os.path.dirname(console.logfile), pcvs.NAME_LOG_FILE)
    console.setoutfile(open(logfile, "w", encoding="utf-8"))


def capture_exception(
    e_type, user_func: Optional[Callable[[Exception], None]] = None, doexit: bool = True
):
    """wraps functions to capture unhandled exceptions for high-level
    function not to crash.
    :param e_type: errors to be caught
    :type: e_type: Exception
    :param user_func: Optional, a function to call to manage the exception
    :type: a function pointer
    :return: function handler to manage exception
    :rtype: function pointer
    """

    def inner_function(func):
        """wrapper for inner function using try/except to avoid crashing

        :param func: function to wrap
        :type func: function
        :return: wrapper
        :rtype: function
        """

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            """functools wrapping function

            :param args: arguments forwarded to wrapped func
            :type args: list
            :param kwargs: arguments forwarded  to wrapped func
            :type kwargs: dict
            :return: result of wrapped function
            :rtype: any
            """
            try:
                return func(*args, **kwargs)
            except e_type as e:
                if user_func is None:
                    assert console
                    console.exception(e)
                    console.error(f"[red bold]Exception: {e}[/]")
                    console.error(
                        f"[red bold]See '{pcvs.NAME_DEBUG_FILE}'"
                        f" or rerun with -vv for more details[/]"
                    )
                    if doexit:
                        sys.exit(1)
                else:
                    user_func(e)

        return wrapper

    return inner_function
