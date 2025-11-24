class PCVSException(Exception):
    """Generic PCVS error (custom errors will inherit of this)."""

    def __init__(
        self,
        reason,
        help_msg=None,
        dbg_info={},
    ):
        """Constructor for generic errors.
        :param *args: unused
        :param **kwargs: messages for the error.
        """
        self._help_msg = help_msg
        self._dbg_info = dbg_info
        super().__init__("{} - {}".format(type(self).__name__, reason))

    def __str__(self):
        """Stringify an exception for pretty-printing.

        :return: the string.
        :type: str
        """
        name_msg = super().__str__() + "\n"
        help_msg = f"{self._help_msg}\n" if self._help_msg else ""
        dbg_msg = "Additional notes:\n" + self.__dbg_str() + "\n" if self._dbg_info else ""
        cause_msg = f"From:\n{self.__cause__}" if self.__cause__ is not None else ""
        return f"{name_msg}{help_msg}{dbg_msg}{cause_msg}"

    def add_dbg(self, **kwargs):
        for k, v in kwargs.items():
            if k not in self._dbg_info:
                self._dbg_info[k] = v

    def __dbg_str(self) -> str:
        """
        Stringify the debug infos. These infos are stored as a dict initially.

        :return: a itemized string.
        :rtype: str
        """
        if not self._dbg_info:
            return ""
        w = max(len(k) for k in self._dbg_info.keys())
        return "\n".join([f"- {k:<{w}}: {v}" for k, v in self._dbg_info.items()])


class CommonException(PCVSException):
    """Gathers exceptions commonly encountered by more specific namespaces."""

    class NotPCVSRelated(PCVSException):
        pass

    class AlreadyExistError(PCVSException):
        """The content already exist as it should."""

        def __init__(self, reason="Already Exist", **kwargs):
            """Updated constructor"""
            super().__init__(
                reason=reason,
                help_msg="\n".join(
                    [
                        "Note configuration, profiles & pcvs.* files can be ",
                        "verified through `pcvs check [-C|-P|-D <path>]`",
                    ]
                ),
                dbg_info=kwargs,
            )

    class UnclassifiableError(PCVSException):
        """Unable to classify this common error."""

    class NotFoundError(PCVSException):
        """Content haven't been found based on specifications."""

    class IOError(PCVSException):
        """Communication error (FS, process) while processing data."""

    class WIPError(PCVSException):
        """Work in Progress, not a real error."""

    class TimeoutError(PCVSException):
        """The parent class timeout error."""

    class NotImplementedError(PCVSException):
        """Missing implementation for this particular feature."""


class BankException(CommonException):
    "Bank-specific exceptions." ""

    class NotFoundError(PCVSException):
        """Bank not Found."""

    class ProjectNameError(PCVSException):
        """name is not a valid project under the given bank."""


class ConfigException(CommonException):
    """Config-specific exceptions."""


class ProfileException(CommonException):
    """Profile-specific exceptions."""

    class IncompleteError(PCVSException):
        """A configuration block is missing to build the profile."""


class ValidationException(PCVSException):
    """Validation-specific exceptions."""

    class YamlError(PCVSException):
        """An error ocured when parsing an Invalid yaml structure."""

        def __init__(self, file: str, content: str):
            """Updated Constructor"""
            super().__init__(reason="Fail to load the following yaml")
            self.add_dbg(file_path=file, raw_yaml=content)

    class SetupError(PCVSException):
        """An error ocured when run pcvs.setup file."""

        def __init__(self, file: str):
            super().__init__(reason="Fail to run the following setup file")
            self.add_dbg(file_path=file)

    class FormatError(PCVSException):
        """The content does not comply the required format (schemes)."""

        def __init__(self, reason="Invalid format", **kwargs):
            """Updated constructor"""
            super().__init__(
                reason=reason,
                help_msg="\n".join(["Input files may be checked with `pcvs check`"]),
                dbg_info=kwargs,
            )

    class WrongTokenError(PCVSException):
        """A unknown token is found in valided content"""

        def __init__(self, reason="Invalid token(s) used as Placeholders", **kwargs):
            """Updated constructor"""
            super().__init__(
                reason=reason,
                help_msg="\n".join(["A list of valid tokens is available in the documentation"]),
                dbg_info=kwargs,
            )

    class SchemeError(PCVSException):
        """The content is not a valid format (scheme)."""

        def __init__(self, reason="Invalid Scheme provided", **kwargs):
            """Updated constructor"""
            super().__init__(
                reason=reason,
                help_msg="\n".join(
                    [
                        "Provided schemes should be static. If code haven't be",
                        "changed, please report this error.",
                    ]
                ),
                dbg_info=kwargs,
            )


class RunException(CommonException):
    """Run-specific exceptions."""

    class InProgressError(PCVSException):
        """A run is currently occurring in the given dir."""

        def __init__(self, reason="Build directory currently used by another instance", **kwargs):
            """Updated constructor"""
            super().__init__(
                reason=reason,
                help_msg="\n".join(
                    [
                        "Please Wait for previous executions to complete.",
                        "You may also use --override or --output to change default build directory",
                    ]
                ),
                dbg_info=kwargs,
            )

    class NonZeroSetupScript(PCVSException):
        """a setup script (=pcvs.setup) completed but returned non-zero exit code."""

        def __init__(self, reason="A setup script failed to complete", **kwargs):
            """Updated constructor"""
            super().__init__(
                reason=reason,
                help_msg="\n".join(["Try to run manually the setup script"]),
                dbg_info=kwargs,
            )

    class ProgramError(PCVSException):
        """The given program cannot be found."""

        def __init__(self, reason="A program cannot be found", **kwargs):
            """Updated constructor"""
            super().__init__(
                reason=reason,
                help_msg="\n".join(
                    [
                        "A program/binary defined in loaded profile cannot",
                        "be found in $PATH or spack/module. Please report",
                        "if this is a false warning.",
                    ]
                ),
                dbg_info=kwargs,
            )


class TestException(CommonException):
    """Test-specific exceptions."""

    class TestExpressionError(PCVSException):
        """Test description is wrongly formatted."""

        def __init__(
            self, input_files, reason="Issue(s) while parsing a Test Descriptor", **kwargs
        ):
            """Updated constructor"""
            super().__init__(
                reason=reason,
                help_msg="\n".join(
                    ["Please check input files with `pcvs check`", "Invalid files are:", "{}"]
                ).format("\n".join(input_files)),
                dbg_info=kwargs,
            )


class OrchestratorException(CommonException):
    """Execution-specific errors."""

    class UndefDependencyError(PCVSException):
        """Declared job dep cannot be fully qualified, not defined."""

    class CircularDependencyError(PCVSException):
        """Circular dep detected while processing job dep tree."""


class RunnerException(CommonException):
    """RunnerException"""

    class LaunchError(PCVSException):
        """Unable to run a remote container"""


class PublisherException(CommonException):
    """PublisherException"""

    class BadMagicTokenError(PCVSException):
        """Issue with token stored to file to check consistency"""

    class UnknownJobError(PCVSException):
        """Unable to identify a job by its ID"""

    class AlreadyExistJobError(PCVSException):
        """A single ID leads to multiple jobs."""


class LockException(CommonException):
    """Lock-specific exceptions."""

    class BadOwnerError(PCVSException):
        """Attempt to manipulate the lock while the current process is not the
        owner."""

    class TimeoutError(PCVSException):
        """Timeout reached before lock."""


class PluginException(CommonException):
    """Plugin-related exceptions."""

    class BadStepError(PCVSException):
        """targeted pass does not exist."""

    class LoadError(PCVSException):
        """Unable to load plugin directory."""

        def __init__(self, reason="Issue(s) while loading plugin", **kwargs):
            """Updated constructor"""
            super().__init__(
                reason=reason,
                help_msg="\n".join(
                    [
                        "Please ensure plugins can be imported like:",
                        "python3 ./path/to/plugin/file.py",
                    ]
                ),
                dbg_info=kwargs,
            )


class GitException(CommonException):
    """GitException"""

    class BadEntryError(PCVSException):
        """BadEntryError"""
