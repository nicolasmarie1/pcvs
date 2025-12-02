from pcvs.converter import yaml_converter

try:
    import rich_click as click

    click.rich_click.SHOW_ARGUMENTS = True
except ImportError:
    import click  # type: ignore


@click.command(
    name="convert",
    short_help="YAML to YAML converter",
)
@click.option(
    "-k",
    "--kind",
    "kind",
    type=click.Choice(
        ["compiler", "runtime", "environment", "te", "profile"], case_sensitive=False
    ),
    required=True,
    help="Select a kind to apply for the file",
)
@click.option(
    "-t",
    "--template",
    "template",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    required=False,
    default=None,
    help="Optional template file (=group) to resolve aliases",
)
@click.option(
    "-s",
    "--scheme",
    "scheme",
    required=False,
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Override default spec by custom one",
)
@click.option(
    "-o",
    "--output",
    "out",
    default=None,
    type=click.Path(exists=False, dir_okay=False),
    help="Filepath where to put the converted YAML",
)
@click.option(
    "--stdout",
    "stdout",
    is_flag=True,
    default=False,
    help="Print the stdout nothing but the converted data",
)
@click.option(
    "--skip-unknown",
    "skip_unknown",
    default=False,
    is_flag=True,
    help="Missing keys are ignored and kept as is in final output",
)
@click.option(
    "--in-place",
    "in_place",
    is_flag=True,
    default=False,
    help="Write conversion back to the original file (DESTRUCTIVE)",
)
@click.argument(
    "input_file",
    type=click.Path(
        exists=True,
        dir_okay=False,
        readable=True,
        allow_dash=True,
    ),
)
@click.pass_context
def convert(
    ctx: click.Context,  # pylint: disable=unused-argument
    input_file: click.Path,
    kind: str,
    template: click.Path,
    scheme: click.Path,
    out: click.Path,
    stdout: bool,
    skip_unknown: bool,
    in_place: bool,
) -> None:
    """Convert cli."""
    yaml_converter.convert(input_file, kind, template, scheme, out, stdout, skip_unknown, in_place)
