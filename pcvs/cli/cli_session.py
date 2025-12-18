import os
from datetime import datetime
from datetime import timedelta

from rich.table import Table
from typeguard import typechecked

from pcvs import io
from pcvs import NAME_BUILDFILE
from pcvs.backend import session as pvSession
from pcvs.helpers import utils

try:
    import rich_click as click

    click.rich_click.SHOW_ARGUMENTS = True
except ImportError:
    import click  # type: ignore

from click.shell_completion import CompletionItem


@typechecked
def compl_session_token(
    ctx: click.Context, param: click.Parameter, incomplete: str  # pylint: disable=unused-argument
) -> list:
    """Session name completion function.

    :param ctx: Click context
    :param args: the option/argument requesting completion.
    :param incomplete: the user input
    """

    sessions = pvSession.list_alive_sessions()
    if sessions is None:
        return []
    return [
        CompletionItem(k, help=str(pvSession.SessionState(v["state"])))
        for k, v in sessions.items()
        if incomplete in str(k)
    ]


@typechecked
def print_sessions(sessions: dict[str, dict]) -> None:
    """
    List detached sessions.

    :param sessions: dict of sessions id, and sessions data.
    """
    if len(sessions) <= 0:
        io.console.print("[italic bold]No sessions")
        return
    table = Table(title="Sessions", expand=True)
    table.add_column("SID", justify="center", max_width=10)
    table.add_column("Status", justify="right")
    table.add_column("Started", justify="center")
    table.add_column("Elapsed", justify="right")
    table.add_column("Location", justify="left")

    for sk, sv in sessions.items():
        s = pvSession.Session()
        s.load_from(sk, sv)
        status = "Broken"
        duration = timedelta()
        line_style = "default"
        if s.state == pvSession.SessionState.IN_PROGRESS:
            duration = datetime.now() - s.property("started")
            status = "{:3.2f} %".format(s.property("progress"))
            line_style = "yellow"
        elif s.state == pvSession.SessionState.COMPLETED:
            duration = s.property("ended") - s.property("started")
            status = "100.00 %"
            line_style = "green bold"
        elif s.state == pvSession.SessionState.WAITING:
            duration = datetime.now() - s.property("started")
            status = "Waiting"
            line_style = "yellow"

        table.add_row(
            "[{}]{:0>6}".format(line_style, s.id),
            "[{}]{}".format(line_style, status),
            "[{}]{}".format(line_style, datetime.strftime(s.property("started"), "%Y-%m-%d %H:%M")),
            "[{}]{}".format(
                "red bold" if duration.days > 0 else line_style,
                timedelta(days=duration.days, seconds=duration.seconds),
            ),
            "[{}]{}".format(line_style, s.property("path")),
        )
    io.console.print(str(table))


@click.command(name="session", short_help="Manage multiple validations")
@click.option(
    "-c",
    "--clear",
    "ack",
    type=str,
    default=None,
    help="Clear a 'completed' remote session, for removing from logs",
)
@click.option(
    "-C",
    "--clear-all",
    "ack_all",
    is_flag=True,
    default=False,
    help="Clear all completed sessions, for removing from logs",
)
@click.option(
    "-l",
    "--list",
    "list_sessions",
    is_flag=True,
    help="List detached sessions",
)
@click.pass_context
@typechecked
def session(
    ctx: click.Context,  # pylint: disable=unused-argument
    ack: str,
    ack_all: bool,
    list_sessions: bool,
) -> None:
    """Manage sessions by listing or acknowledging their completion."""
    sessions = pvSession.list_alive_sessions()
    if sessions is None:
        sessions = {}

    if ack_all is True:
        for session_id, session_obj in sessions.items():
            if session_obj["state"] != pvSession.SessionState.IN_PROGRESS:
                pvSession.remove_session_from_file(session_id)
                lockfile = os.path.join(session_obj["path"], NAME_BUILDFILE)
                utils.unlock_file(lockfile)
    elif ack is not None:
        if ack not in sessions:
            raise click.BadOptionUsage("--ack", "No such Session id (see pcvs session)")
        elif sessions[ack]["state"] not in [
            pvSession.SessionState.ERROR,
            pvSession.SessionState.COMPLETED,
        ]:
            raise click.BadOptionUsage("--ack", "This session is not completed yet")

        pvSession.remove_session_from_file(ack)
        lockfile = os.path.join(sessions[ack]["path"], NAME_BUILDFILE)
        utils.unlock_file(lockfile)
    elif list_sessions:
        print_sessions(sessions)
    else:  # listing is the default
        print_sessions(sessions)
