import os
import sys
from datetime import datetime

from typeguard import typechecked

from pcvs import io
from pcvs import NAME_BUILDFILE
from pcvs import NAME_RUN_CONFIG_FILE
from pcvs.backend import bank as pvBank
from pcvs.backend import run as pvRun
from pcvs.backend import session as pvSession
from pcvs.backend.configfile import Profile as pvProfile
from pcvs.backend.metaconfig import GlobalConfig
from pcvs.backend.metaconfig import MetaConfig
from pcvs.cli import cli_bank
from pcvs.helpers import exceptions
from pcvs.helpers import utils
from pcvs.helpers.storage import ConfigDesc
from pcvs.helpers.storage import ConfigKind
from pcvs.helpers.storage import ConfigLocator

try:
    import rich_click as click

    click.rich_click.SHOW_ARGUMENTS = True
except ImportError:
    import click  # type: ignore

from click.shell_completion import CompletionItem


@typechecked
def iterate_dirs(
    ctx: click.Context,  # pylint: disable=unused-argument
    param: click.Parameter,  # pylint: disable=unused-argument
    value: tuple[str, ...],
) -> dict[str, str] | None:
    """Validate directories provided by users & format them correctly.

    Set the default label for a given path if not specified & Configure default
    directories if none was provided.

    :param ctx: Click Context
    :param param: The param targeting the function
    :param value: The value given by the user:
    :return: properly formatted dict of user directories, keys are labels.
    """
    dirs: dict[str, str] = {}
    if value is None:  # if not specified
        return None

    err_msg = ""
    for d in value:
        testpath = os.path.abspath(d)
        label = os.path.basename(testpath)

        # if label already used for a different path
        if label in dirs.keys() and testpath != dirs[label]:
            err_msg += "- '{}': Used more than once\n".format(label.upper())
        elif not os.path.isdir(testpath):
            err_msg += "- '{}': No such directory\n".format(testpath)
        # else, add it
        else:
            dirs[label] = testpath
    if len(err_msg) > 0:
        raise click.BadArgumentUsage(
            "\n".join(
                [
                    "While parsing user directories:",
                    "{}".format(err_msg),
                    "please see '--help' for more information",
                ]
            )
        )
    return dirs


@typechecked
def compl_list_dirs(
    ctx: click.Context, param: click.Parameter, incomplete: str  # pylint: disable=unused-argument
) -> list[CompletionItem]:
    """directory completion function.

    :param ctx: Click context
    :type ctx: :class:`Click.Context`
    :param param: the option/argument requesting completion.
    :type param: click.Parameter
    :param incomplete: the user input
    :type incomplete: str
    """
    obj = click.Path(exists=True, dir_okay=True, file_okay=False)
    return obj.shell_complete(ctx, param, incomplete)


@typechecked
def compl_list_profiles(
    ctx: click.Context, param: click.Parameter, incomplete: str  # pylint: disable=unused-argument
) -> list[str]:
    """All profiles name completion function."""
    return [
        elt.full_name
        for elt in ConfigLocator().list_configs(kind=ConfigKind.PROFILE)
        if incomplete in elt.full_name
    ]


@typechecked
def handle_build_lockfile(exc: Exception | None = None) -> None:
    """Remove the file lock in build dir if the application stops abruptly.

    This function will automatically forward the raising exception to the next
    handler.

    :raises Exception: Any exception triggering this handler
    :param exc: The raising exception.
    :type exc: Exception
    """
    if (
        GlobalConfig.root
        and "validation" in GlobalConfig.root
        and "output" in GlobalConfig.root["validation"]
    ):
        prefix = os.path.join(GlobalConfig.root["validation"]["output"], NAME_BUILDFILE)
        if utils.is_locked(prefix):
            if utils.get_lock_owner(prefix)[1] == os.getpid():
                utils.unlock_file(prefix)

    if exc:
        raise exc


@typechecked
def parse_tags(filters: str) -> dict[str, bool]:
    """Parse input to generate tags set."""
    tags = {}
    for f in filters.split(","):
        if len(f) == 0:
            continue
        if f[0] == "!":
            tags[f[1:]] = False
        else:
            tags[f] = True
    return tags


@click.command(
    name="run",
    short_help="Run a validation",
)
@click.option(
    "-p",
    "--profile",
    "profilename",
    default=None,
    shell_complete=compl_list_profiles,
    type=str,
    show_envvar=True,
    help="Existing and valid profile supporting this run",
)
@click.option(
    "-o",
    "--output",
    "output",
    default=None,
    show_envvar=True,
    type=click.Path(exists=False, file_okay=False),
    help="F directory where PCVS is allowed to store data",
)
@click.option(
    "-c",
    "--settings-file",
    "settings_file",
    default=None,
    show_envvar=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
    help="Invoke file gathering validation options",
)
@click.option(
    "--detach",
    "detach",
    default=False,
    is_flag=True,
    show_envvar=True,
    help="Run the validation asynchronously (WIP)",
)
@click.option(
    "-f/-F",
    "--override/--no-override",
    "override",
    default=False,
    is_flag=True,
    show_envvar=True,
    help="Allow to reuse an already existing output directory",
)
@click.option(
    "-d",
    "--dry-run",
    "simulated",
    default=False,
    is_flag=True,
    help="Reproduce the whole process without running tests",
)
@click.option(
    "-a",
    "--anonymize",
    "anon",
    default=False,
    is_flag=True,
    help="Purge the results from sensitive data (HOME, USER...)",
)
@click.option(
    "-b",
    "--bank",
    "bank",
    default=None,
    shell_complete=cli_bank.compl_bank_projects,
    help="Which bank will store the run in addition to the archive",
)
@click.option(
    "-m",
    "--message",
    "msg",
    default=None,
    help="Message to store the run (if bank is enabled)",
)
@click.option(
    "--duplicate",
    "dup",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    required=False,
    help="Reuse old test directories (no DIRS required)",
)
@click.option(
    "-r",
    "--report",
    "enable_report",
    show_envvar=True,
    is_flag=True,
    default=False,
    help="Attach a webview server to the current session run.",
)
@click.option(
    "--report-uri",
    "report_addr",
    default=None,
    type=str,
    help="Override default Server address",
)
@click.option(
    "-g",
    "--generate-only",
    "generate_only",
    is_flag=True,
    default=False,
    help="Rebuild the test-base, populating resources for `pcvs exec`",
)
@click.option(
    "-t",
    "--timeout",
    "timeout",
    show_envvar=True,
    type=int,
    default=None,
    help="PCVS process timeout",
)
@click.option(
    "-S",
    "--successful",
    "only_success",
    is_flag=True,
    default=False,
    help="Return non-zero exit code if a single test has failed",
)
@click.option(
    "-s",
    "--spack-recipe",
    "spack_recipe",
    type=str,
    default=None,
    multiple=True,
    help="Build test-suites based on Spack recipes",
)
@click.option(
    "-P",
    "--print",
    "print_policy",
    type=click.Choice(["none", "errors", "all"]),
    default=None,
    help="Policy for printing tests output depending on its status",
)
@click.option(
    "-T",
    "--print-filter",
    "print_filter",
    type=str,
    default="",
    help="Filter test output based on a list of tags.",
)
@click.option(
    "-R",
    "--run-filter",
    "run_filter",
    type=str,
    default="",
    help="Filter which tests are run based on a list of tags.",
)
@click.argument(
    "dirs",
    nargs=-1,
    type=str,
    callback=iterate_dirs,
)
@click.pass_context
@io.capture_exception(Exception)
@io.capture_exception(Exception, handle_build_lockfile)
@io.capture_exception(KeyboardInterrupt, handle_build_lockfile)
@typechecked
def run(
    ctx: click.Context,
    profilename: str | None,
    output: str | None,
    settings_file: str | None,
    detach: bool,
    override: bool,
    simulated: bool,
    anon: bool,
    bank: str | None,
    msg: str | None,
    dup: str | None,
    enable_report: bool,
    report_addr: str | None,
    generate_only: bool,
    timeout: int | None,
    only_success: bool,
    spack_recipe: tuple[str, ...] | None,
    print_policy: str | None,
    print_filter: str,
    run_filter: str,
    dirs: dict[str, str],  # see callback function for type infos
) -> None:
    """
    Execute a validation suite from a given PROFILE.

    By default the current directory is scanned to find test-suites to run.
    May also be provided as a list of directories as described by tests
    found in DIRS.

    Warning: Tags filters are order sensitive, a test with 'compiler' and 'test' tags
    will be filter out by '!test,compiler' but included by 'compiler,!test'.
    (The first tag in the filter to match a tag in the test rule).
    """

    io.console.info("PRE-RUN: start")
    # first, prepare raw arguments to be usable
    if output is not None:
        output = os.path.abspath(output)

    global_config = MetaConfig()
    GlobalConfig.root = global_config
    global_config.set_internal("pColl", ctx.obj["plugins"])

    # then init the configuration
    if settings_file is None:
        # detect ?
        detect = os.path.join(os.getcwd(), NAME_RUN_CONFIG_FILE)
        settings_file = detect if os.path.isfile(detect) else None
    io.console.debug("PRE-RUN: load settings from local file: {}".format(settings_file))
    global_config.bootstrap_validation_from_file(settings_file)
    val_cfg = global_config["validation"]

    # save 'run' parameters into global configuration
    val_cfg.set_ifdef("datetime", datetime.now())
    val_cfg.set_ifdef("print_policy", print_policy)
    val_cfg.set_ifdef("print_filter", parse_tags(print_filter))
    val_cfg.set_ifdef("run_filter", parse_tags(run_filter))
    val_cfg.set_ifdef("color", ctx.obj["color"])
    val_cfg.set_ifdef("output", output)
    val_cfg.set_ifdef("background", detach)
    val_cfg.set_ifdef("override", override)
    val_cfg.set_ifdef("simulated", simulated)
    val_cfg.set_ifdef("onlygen", generate_only)
    val_cfg.set_ifdef("anonymize", anon)
    val_cfg.set_ifdef("reused_build", dup)
    val_cfg.set_ifdef("default_profile", profilename)
    val_cfg.set_ifdef("target_bank", bank)
    val_cfg.set_ifdef("message", msg)
    val_cfg.set_ifdef("enable_report", enable_report)
    val_cfg.set_ifdef("report_addr", report_addr)
    val_cfg.set_ifdef("timeout", timeout)
    val_cfg.set_ifdef("spack_recipe", spack_recipe)
    val_cfg.set_ifdef("only_success", only_success)
    val_cfg.set_ifdef("buildcache", os.path.join(val_cfg["output"], "cache"))

    # if dirs not set by config file nor CLI
    if not dirs and not val_cfg["dirs"]:
        dirs = {}
        if not spack_recipe:
            testpath = os.getcwd()
            dirs = {os.path.basename(testpath): testpath}

    # not overriding if dirs is None
    val_cfg.set_ifdef("dirs", dirs)

    if bank is not None:
        obj = pvBank.Bank(bank)
        io.console.debug("PRE-RUN: configure target bank: {}".format(obj.name))
        obj.disconnect()

    # BEFORE the build dir still does not exist !
    buildfile = os.path.join(val_cfg["output"], NAME_BUILDFILE)
    if os.path.exists(val_cfg["output"]):
        # careful if the build dir does not exist
        # the condition above may be executed concurrently
        # by two runs, inducing parallel execution in the same dir
        # TODO.
        if not utils.trylock_file(buildfile):
            if val_cfg["override"]:
                utils.lock_file(buildfile, force=True)
            else:
                raise exceptions.RunException.InProgressError(
                    path=val_cfg["output"],
                    lockfile=buildfile,
                    owner_pid=str(utils.get_lock_owner(buildfile)),
                )

    elif not os.path.exists(val_cfg["output"]):
        io.console.debug("PRE-RUN: Prepare output directory: {}".format(val_cfg["output"]))
        os.makedirs(val_cfg["output"])

    # check if another build should reused
    # this avoids to re-run combinatorial system twice
    if val_cfg["reused_build"] is not None:
        io.console.info("PRE-RUN: Clone previous build to be reused")
        try:
            io.console.debug("PRE-RUN: previous build: {}".format(val_cfg["reused_build"]))
            global_config = pvRun.dup_another_build(val_cfg["reused_build"], val_cfg["output"])
            # TODO: Currently nothing can be overridden from cloned build except:
            # - 'output'
        except FileNotFoundError as fnfe:
            raise click.BadOptionUsage(
                "--duplicate", "{} is not a valid build directory!".format(val_cfg["reused_build"])
            ) from fnfe
    else:
        cl: ConfigLocator = ConfigLocator()
        cd: ConfigDesc = cl.parse_full_raise(
            val_cfg["default_profile"], kind=ConfigKind.PROFILE, should_exist=True
        )
        pf = pvProfile(cd, cl)

        val_cfg.set_ifdef("pf_name", pf.full_name)
        global_config.bootstrap_from_profile(pf)

    the_session = pvSession.Session(val_cfg["datetime"], val_cfg["output"])
    the_session.register_callback(callback=pvRun.process_main_workflow)

    io.console.info("PRE-RUN: Session to be started")
    if val_cfg["background"]:
        sid = the_session.run_detached(the_session)
        print("Session successfully started, ID {}".format(sid))
    else:
        sid = the_session.run(the_session)
        utils.unlock_file(buildfile)

    final_rc = the_session.rc if only_success else 0
    sys.exit(final_rc)
