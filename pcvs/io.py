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
import rich.box as box
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


class TheConsole(Console):
    """
    Main interface to print information to users.

    Any output from the application should be handled by this Console.

    :param Console: Rich base class
    :type Console: Console
    """

    def __init__(self, **kwargs) -> None:
        """
        Build a new Console.

        Many options to configure the console:
        - color: boolean (color support)
        - verbose: boolean (verbose msg mode in log files)
        - stderr: boolean (print to stdout by default)
        Any other argument is considered a base class options.

        :param args: any argument to be forwarded to Rich console, as list
        :type args: list
        :param kwargs: any argument to be forwarded to Rich Console as dict
        :type kwargs: dict
        """
        self._display_table = None
        self._progress = None
        self._singletask = None
        self.live = None

        self._color = "auto" if kwargs.get("color", True) else None
        self._verbose = Verbosity(min(Verbosity.NB_LEVELS - 1, kwargs.get("verbose", 0)))
        self._debugfile = open(os.path.join(".", pcvs.NAME_DEBUG_FILE), "w", encoding="utf-8")
        self.summary_table: Dict[str, Dict[str, Dict[str, int]]] = {}
        err = kwargs.get("stderr", False)
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

        super().__init__(color_system=self._color, theme=theme, stderr=err)
        self._debugconsole = Console(
            file=self._debugfile,
            theme=theme,
            color_system=self._color,
            markup=self._color is not None,
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
        self._chars = SpecialChar(utf_support=self.encoding.startswith("utf"))

        # Activate when needed
        self._sched_debug = False
        self._crit_debug = False

    @property
    def logfile(self):
        """
        Get the path to the logging file

        :return: the logging file
        :rtype: str
        """
        return os.path.abspath(self._debugfile.name)

    @property
    def outfile(self):
        """
        Get the path where the Console output is logged (disabled by default)

        :return: the file path
        :rtype: str
        """
        return os.path.abspath(self.file.name)

    @property
    def verbose(self):
        """
        Get verbose status.

        :return: the status
        :rtype: integer
        """
        return self._verbose

    def verb_level(self, level):
        """
        Test if a given level is logged by the current console

        :param level: the targeted level
        :type level: Verbosity
        :return: True if this level is logged, false otherwise
        :rtype: boolean
        """
        return self._verbose >= level

    @property
    def verb_compact(self):
        """
        Return true if at least COMPACT debug level is enabled.

        :return: a boolean to check debug level
        :rtype: boolean
        """
        return self.verb_level(Verbosity.COMPACT)

    @property
    def verb_detailed(self):
        """
        Return true if at least DETAILED debug level is enabled.

        :return: a boolean to check debug level
        :rtype: boolean
        """
        return self.verb_level(Verbosity.DETAILED)

    @property
    def verb_info(self):
        """
        Return true if at least INFO debug level is enabled.

        :return: a boolean to check debug level
        :rtype: boolean
        """
        return self.verb_level(Verbosity.INFO)

    @property
    def verb_debug(self):
        """
        Return true if at least DEBUG debug level is enabled.

        :return: a boolean to check debug level
        :rtype: boolean
        """
        return self.verb_level(Verbosity.DEBUG)

    @verbose.setter
    def verbose(self, v):
        self._verbose = v

    def __del__(self):
        if self._debugfile:
            self._debugfile.close()
            self._debugfile = None

    def move_debug_file(self, newdir):
        assert os.path.isdir(newdir)
        if self._debugfile:
            shutil.move(self._debugfile.name, os.path.join(newdir, pcvs.NAME_DEBUG_FILE))
        else:
            self.warning("No '{}' file found for this Console".format(pcvs.NAME_DEBUG_FILE))

    def print_section(self, txt):
        self.print("[yellow bold]{} {}[/]".format(self.utf("sec"), txt), soft_wrap=True)
        self._loghdl.info("[DISPLAY] ======= %s ======", txt)

    def print_header(self, txt):
        self.rule("[green bold]{}[/]".format(txt.upper()))
        self._loghdl.info("[DISPLAY] ------- %s ------", txt)

    def print_item(self, txt, depth=1):
        self.print(
            "[red bold]{}{}[/] {}".format(" " * (depth * 2), self.utf("item"), txt), soft_wrap=True
        )
        self._loghdl.info("[DISPLAY] * %s", txt)

    def print_box(self, txt, *args, **kwargs):
        self.print(Panel.fit(txt, *args, **kwargs))

    def print_job(
        self,
        state,
        time,
        tlabel,
        tsubtree,
        tname,
        timeout=0,
        colorname="red",
        icon=None,
        content=None,
    ):
        if icon is not None:
            icon = self.utf(icon)

        if self._verbose >= Verbosity.DETAILED:
            self.print(
                "[{} bold]   {} {:8.2f}s{}{:7}{}{}{}".format(
                    colorname,
                    icon,
                    time,
                    self.utf("sep_v"),
                    state,
                    f" ({timeout:5.2f}s)" if timeout > 0 else "",
                    self.utf("sep_v"),
                    tname,
                )
            )
            if content:
                # print raw input
                # parsing on uncontrolled output may lead to errors
                self.out(content)
        else:
            self.summary_table.setdefault(tlabel, {})
            self.summary_table[tlabel].setdefault(
                tsubtree,
                {
                    label: 0
                    for label in [
                        "SUCCESS",
                        "FAILURE",
                        "ERR_DEP",
                        "HARD_TIMEOUT",
                        "SOFT_TIMEOUT",
                        "ERR_OTHER",
                    ]
                },
            )

            self.summary_table[tlabel][tsubtree][state] += 1

            def regenerate_table():
                table = Table(expand=True, box=box.SIMPLE)
                table.add_column("Name", justify="left", ratio=10)
                table.add_column("SUCCESS", justify="center")
                table.add_column("FAILURE", justify="center")
                table.add_column("ERR_DEP", justify="center")
                table.add_column("HARD_TIMEOUT", justify="center")
                table.add_column("SOFT_TIMEOUT", justify="center")
                table.add_column("ERR_OTHER", justify="center")
                for label, lvalue in self.summary_table.items():
                    for subtree, svalue in lvalue.items():
                        if sum(svalue.values()) == svalue.get("SUCCESS", 0):
                            colour = "green"
                        elif svalue.get("FAILURE", 0) > 0:
                            colour = "red"
                        else:
                            colour = "yellow"
                        columns_list = ["[{} bold]{}".format(colour, x) for x in svalue.values()]
                        table.add_row("[{} bold]{}{}".format(colour, label, subtree), *columns_list)
                return table

            self._reset_display_table(regenerate_table())
        self._progress.advance(self._singletask)
        self.live.update(self._display_table)

    def _reset_display_table(self, table):
        self._display_table = Table.grid(expand=True)
        self._display_table.add_row(table)
        self._display_table.add_row(Panel(self._progress))

    def table_container(self, total) -> Live:
        self._progress = Progress(
            TimeElapsedColumn(),
            "Progress",
            BarColumn(bar_width=None, complete_style="yellow", finished_style="green"),
            TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
            SpinnerColumn(speed=0.5),
            expand=True,
        )
        self._singletask = self._progress.add_task("Progress", total=int(total))

        self._reset_display_table(Table())
        self.live = Live(self._display_table, console=self)
        return self.live

    def create_table(self, title, cols) -> Table:
        return Table(*cols, title=title)

    def progress_iter(self, it: Iterable, **kwargs) -> Iterable:
        """prints a progress bar using click

        :param it: iterable on which the progress bar has to iterate
        :type it: Iterable
        :param kwargs: any extra info forwarded to click progress bar handler
        :type kwargs: dict
        :return: a click progress bar (iterable)
        :rtype: Iterable
        """
        global console
        return track(
            it,
            transient=True,
            console=console,
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

        if self.size.width < 40:
            banner = logo_minimal
        elif self.size.width < 95:
            banner = logo_short

        self.print("\n".join(banner))
        pcvs_version = version("pcvs")
        self.print(f"Parallel Computing Validation System (pcvs) -- version {pcvs_version}")

    def nodebug(self, fmt, *args, **kwargs):
        """Do nothing.

        :param fmt: fmt
        :param *args: args
        :param **kwargs: kwargs
        """

    def debug(self, fmt, *args, **kwargs):
        """Print & log debug.

        :param fmt: fmt
        :param *args: args
        :param **kwargs: kwargs
        """
        self._loghdl.debug(fmt, *args, **kwargs)
        if self._verbose >= Verbosity.DEBUG:
            user_fmt = fmt.format(*args, **kwargs) if args or kwargs else fmt
            self.print(f"[debug]\\[debug]: {user_fmt}[/debug]", soft_wrap=True)

    def info(
        self,
        fmt,
        *args,
        **kwargs,
    ):
        """Print & log info.

        :param fmt: fmt
        :param *args: args
        :param **kwargs: kwargs
        """
        self._loghdl.info(fmt, *args, **kwargs)
        if self._verbose >= Verbosity.INFO:
            user_fmt = fmt.format(*args, **kwargs) if args or kwargs else fmt
            self.print(f"[info]\\[info]: {user_fmt}[/info]", soft_wrap=True)

    def warning(self, fmt, *args, **kwargs):
        """Print & log warning.

        :param fmt: fmt
        :param *args: args
        :param **kwargs: kwargs
        """
        self._loghdl.warning(fmt, *args, **kwargs)
        user_fmt = fmt.format(*args, **kwargs) if args or kwargs else fmt
        self.print(f"[warning]\\[warning]: {user_fmt}[/warning]", soft_wrap=True)

    def warn(self, fmt, *args, **kwargs):
        """Short for warning.

        :param fmt: fmt
        :param *args: args
        :param **kwargs: kwargs
        """
        self.warning(fmt, *args, **kwargs)

    def error(self, fmt, *args, **kwargs):
        """Print a log error.

        :param fmt: fmt
        :param *args: args
        :param **kwargs: kwargs
        """
        self._loghdl.error(fmt, *args, **kwargs)
        user_fmt = fmt.format(*args, **kwargs) if args or kwargs else fmt
        self.print(f"[danger]\\[error]: {user_fmt}[/danger]", soft_wrap=True)

    def critical(self, fmt, *args, **kwargs):
        """Print a log critical error then exit.

        :param fmt: fmt
        :param *args: args
        :param **kwargs: kwargs
        """
        self._loghdl.critical(fmt, *args, **kwargs)
        user_fmt = fmt.format(*args, **kwargs) if args or kwargs else fmt
        self.print(f"[danger]\\[CRITICAL]: {user_fmt}[/danger]", soft_wrap=True)
        sys.exit(42)

    def exception(self, e: BaseException):
        """Print errors.

        :param e: the error to display
        """
        if self._verbose >= Verbosity.DEBUG:
            self.print_exception(word_wrap=True, show_locals=True)
        else:
            self.print_exception(extra_lines=0)
        self._loghdl.exception(e)

    def crit_debug(self, fmt):
        """Print & log debug  for pxcvs scheduler.

        :param fmt: fmt
        :param *args: args
        :param **kwargs: kwargs
        """
        if self._crit_debug:
            self.debug(f"[CRIT]{fmt}")

    def sched_debug(self, fmt):
        """Print & log debug  for pxcvs scheduler.

        :param fmt: fmt
        :param *args: args
        :param **kwargs: kwargs
        """
        if self._sched_debug:
            self.debug(f"[SCHED]{fmt}")

    @property
    def logger(self):
        return self._loghdl


console = None


def init(color=True, verbose=0, *args, **kwargs):
    global console
    console = TheConsole(color=color, verbose=verbose, *args, **kwargs)


def detach_console():
    logfile = os.path.join(os.path.dirname(console.logfile), pcvs.NAME_LOG_FILE)
    console.file = open(logfile, "w", encoding="utf-8")


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
                    console.print(f"[red bold]Exception: {e}[/]")
                    console.print(
                        f"[red bold]See '{pcvs.NAME_DEBUG_FILE}'"
                        f" or rerun with -vv for more details[/]"
                    )
                    if doexit:
                        sys.exit(1)
                else:
                    user_func(e)

        return wrapper

    return inner_function
