import glob
import os
import tempfile
from typing import Optional

import click
from ruamel.yaml import YAML

from pcvs import io
from pcvs import PATH_INSTDIR
from pcvs.backend import config
from pcvs.helpers import git
from pcvs.helpers import system
from pcvs.helpers import utils
from pcvs.helpers.exceptions import ConfigException
from pcvs.helpers.exceptions import ProfileException
from pcvs.helpers.exceptions import ValidationException
from pcvs.helpers.system import MetaDict
from pcvs.converter import yaml_converter

PROFILE_EXISTING = dict()


def init():
    """Initialization callback, loading available profiles on disk.
    """
    global PROFILE_EXISTING
    PROFILE_EXISTING = {}
    # this first loop defines configuration order
    priority_paths = utils.storage_order()
    priority_paths.reverse()
    for token in priority_paths:  # reverse order (overriding)
        PROFILE_EXISTING[token] = []
        for pfile in glob.glob(
                os.path.join(utils.STORAGES[token], 'profile', "*.yml")):
            PROFILE_EXISTING[token].append(
                (os.path.basename(pfile)[:-4], pfile))


def list_profiles(scope=None):
    """Return a list of valid profiles found on disk.

    :param scope: restriction on scope, defaults to None
    :type scope: str, optional
    :return: dict of 3 dicts ('user', 'local' & 'global') or a single dict (if
        'scope' was set), containing, for each profile name, the filepath.
    :rtype: dict
    """
    global PROFILE_EXISTING
    assert (scope in utils.STORAGES.keys() or scope is None)
    if scope is None:
        return PROFILE_EXISTING
    else:
        return PROFILE_EXISTING[scope]


def list_templates():
    """List available templates to be used for boostraping profiles.

    :return: a list of valid templates.
    :rtype: list"""
    array = list()
    for f in os.listdir(os.path.join(PATH_INSTDIR, "templates", "profile")):
        array.append((os.path.splitext(f)[0], f))
    return array


class Profile:
    """ A profile represents the most complete object the user can provide.

    It is built upon 5 components, called configuration blocks (or basic
    blocks), one of each kind (compiler, runtime, machine, criterion & group)
    and gathers all required information to start a validation process. A
    profile object is the basic representation to be manipulated by the user.

    .. note::
        A profile object can be confused with
        :class:`pcvs.helpers.system.MetaConfig`. While both are carrying the
        whole user configuration, a Profile object is used to build/manipulate
        it, while a Metaconfig is the actual internal representation of a
        complete run config.

    :param _name: profile name, should be unique for a given scope
    :type _name: str
    :param _scope: profile scope, allowed values in `storage_order()`, defaults
        to None
    :type _scope: str
    :param _exists: return True if the profile exists on disk.
    :type _exists: bool
    :param _file: profile file absolute path
    :type _file: str
    """

    def __init__(self, name: str = None, profilepath: str = None, scope=None):
        """Constructor method.

        :param name: profile name
        :type name: str
        :param profilepath: profile file path
        :param scope: desired scope, automatically set if not provided
        :type scope: str, optional
        """
        self._details = MetaDict()

        if profilepath:
            self._name = os.path.basename(profilepath.split('\\.')[0])
            self._scope = 'local'
            self._exists = True
            self._file = profilepath
        else:
            utils.check_valid_scope(scope)
            self._name = name
            self._scope = scope
            self._exists = False
            self._file = None
            self._retrieve_file()

    def _retrieve_file(self):
        """From current representation, determine the profile file path.

        This function relies on known profiles & path concatenation.
        """
        self._file = None

        # determine proper scope is not given
        if self._scope is None:
            allowed_scopes = utils.storage_order()
        else:
            allowed_scopes = [self._scope]

        # available profiles lookup to find if it exist.
        for sc in allowed_scopes:
            for pair in PROFILE_EXISTING[sc]:
                if self._name == pair[0]:
                    self._file = pair[1]
                    self._scope = sc
                    self._exists = True
                    return

        # case where the scope were not provided
        # AND no pre-existing profile were found. assume scope as 'local'
        if self._scope is None:
            self._scope = 'local'

        # this code is executed ONLY when a new profile is created
        # otherwise the for loop above would have trigger a profile
        # in that case, _file is computed through path concatenation
        # but the _exists is set to False
        self._file = os.path.join(utils.STORAGES[self._scope], 'profile',
                                  self._name + ".yml")
        self._exists = False

    def get_unique_id(self):
        """Compute unique hash string identifying a profile.

        This is required to make distinction between multiple profiles, based on
        its content (banks relies on such unicity).

        :return: an hashed version of profile content
        :rtype: str
        """
        return git.generate_data_hash(str(self._details))

    def fill(self, raw):
        """Update the given profile with content stored in parameter.

        :param raw: tree of (key, values) pairs to update
        :type raw: dict
        """
        # some checks
        assert isinstance(raw, dict)

        # fill is called either from 'build' (dict of configurationBlock)
        # of from 'clone' (dict of raw file inputs)
        for k, v in raw.items():
            if isinstance(v, config.ConfigurationBlock):
                self._details[k] = MetaDict(v.dump())
            else:
                self._details[k] = v

    def dump(self):
        """Return the full profile content as a single regular dict.

        This function loads the profile on disk first.

        :return: a regular dict for this profile
        :rtype: dict
        """
        # self.load_from_disk()
        return MetaDict(self._details).to_dict()

    def is_found(self):
        """Check if the current profile exists on disk.

        :return: True if the file exist on disk
        :rtype: bool
        """
        return self._exists

    @property
    def scope(self):
        """Return the profile scope.

        :return: profile scope
        :rtype: str
        """
        return self._scope

    @property
    def full_name(self):
        """Return fully-qualified profile name (scope + name).

        :return: the unique profile name.
        :rtype: str
        """
        return ".".join([self._scope, self._name])

    def load_from_disk(self):
        """Load the profile from its representation on disk.

        :raises NotFoundError: profile does not exist
        :raises NotFoundError: profile path is not valid
        """

        if not self._exists:
            raise ProfileException.NotFoundError(self._name)

        if not os.path.isfile(self._file):
            raise ProfileException.NotFoundError(self._file)

        io.console.debug(f"Load {self._name} ({self._scope})")
        with open(self._file, 'r', encoding='utf-8') as f:
            self._details = MetaDict(YAML(typ='safe').load(f))

    def load_template(self, name="default"):
        """Populate the profile from templates of 5 basic config. blocks.

        Filepath still need to be determined via `retrieve_file()` call.

        :param name: the profile template name
        :type name: str, optional
        :raises NotFoundError: target profile isn't found
        """
        self._exists = True
        self._file = None
        filepath = os.path.join(PATH_INSTDIR, "templates", "profile",
                                name) + ".yml"
        if not os.path.isfile(filepath):
            raise ProfileException.NotFoundError(
                f"{name} is not a valid base name.\n"
                "Please use pcvs profile list --all")

        with open(filepath, 'r', encoding='utf-8') as fh:
            self.fill(YAML(typ='safe').load(fh))

    def check(self, allow_legacy: Optional[bool] = True):
        """Ensure profile meets scheme requirements, as a concatenation of 5
        configuration block schemes.

        :param allow_legacy: if the check failed, attempt to validate through
            legacy syntax (recursive call)
        :type allow_legacy: (Optional[str])
        :raises FormatError: A 'kind' is missing from
            profile
        :raises ValidationException.FormatError: incorrect profile.
        """
        try:
            err_dbg = []
            for k in self._details.keys():
                if k not in config.CONFIG_BLOCKS:
                    err_dbg.append(k)
            if err_dbg:
                raise ValidationException.FormatError(
                    "Unknown kind in Profile", invalid_kinds=err_dbg)

            for kind in config.CONFIG_BLOCKS:
                # if kind not in self._details:
                #    raise ValidationException.FormatError(
                #        "Missing '{}' in profile".format(kind))
                system.ValidationScheme(kind).validate(self._details[kind],
                                                       filepath=self._name)
        except ValidationException.FormatError as parsing_error:
            if not allow_legacy:
                raise parsing_error

            tmpfile = tempfile.mkstemp()[1]
            try:
                yaml_converter.convert(None, self._file, 'profile', None,
                                       None, tmpfile, False, True, False)
            except Exception as convert_error:
                io.console.error("An error occure when trying "
                                 f"to update profile: {self._file}")
                raise convert_error from parsing_error

            with open(tmpfile, 'r', encoding='utf-8') as f:
                self._details = MetaDict(YAML(typ='safe').load(f))
            self.check(allow_legacy=False)
            io.console.warning(f"Legacy format for profile '{self._name}'")
            io.console.warning(
                "Please consider updating it with `pcvs_convert -k profile`")

    def flush_to_disk(self):
        """Write down profile to disk.

        Also, ensure the filepath is valid and profile content is compliant with
        schemes.
        """
        self._retrieve_file()
        # self.check()

        # just in case the block subprefix does not exist yet
        prefix_file = os.path.dirname(self._file)
        if not os.path.isdir(prefix_file):
            os.makedirs(prefix_file, exist_ok=True)

        with open(self._file, 'w', encoding='utf-8') as f:
            YAML(typ='safe').dump(self._details.to_dict(), f)

    def clone(self, clone):
        """Duplicate a valid profile into the current one.

        :param clone: a valid profile object
        :type clone: :class:`Profile`
        """
        self._retrieve_file()

        io.console.info("Compute target prefix: {}".format(self._file))
        assert (not os.path.isfile(self._file))
        self._details = clone._details

    def delete(self):
        """Remove the current profile from disk.

        It does not destroy the Python object, though.
        """
        io.console.info("delete {}".format(self._file))
        os.remove(self._file)

    def display(self):
        """Display profile data into stdout/file.
        """
        io.console.print_header("Profile View")
        io.console.print_section("Scope: {}".format(self._scope.capitalize()))
        io.console.print_section("Profile details:")
        if self._details:
            io.console.print_section("Details:")
            for k, v in self._details.items():
                io.console.print_item("{}: {}".format(k, v))

    def edit(self):
        """Open the editor to manipulate profile content.

        :raises Exception: Something happened while editing the file

        .. warning::
            If the edition failed (validation failed) a rejected file is created
            in the current directory containing the rejected profile. Once
            manually edited, it may be submitted again through `pcvs profile
            import`.
        """
        assert self._file is not None

        if not os.path.exists(self._file):
            return

        with open(self._file, 'r', encoding='utf-8') as fh:
            stream = fh.read()

        edited_stream = click.edit(stream, extension=".yml", require_save=True)
        if edited_stream is not None:
            edited_yaml = MetaDict(YAML(typ='safe').load(edited_stream))
            self.fill(edited_yaml)
            self.flush_to_disk()
            try:
                self.check()
            except Exception as e:
                raise e

    def edit_plugin(self):
        """Edit the 'runtime.plugin' section of the current profile.

        :raises Exception: Something happened while editing the file.

        .. warning::
            If the edition failed (validation failed) a rejected file is created
            in the current directory containing the rejected profile. Once
            manually edited, it may be submitted again through `pcvs profile
            import`.
        """
        if not os.path.exists(self._file):
            return

        self.load_from_disk()

        if 'plugin' in self._details['runtime'].keys():
            plugin_code = self._details['runtime']['plugin'].decode('utf-8')
        else:
            plugin_code = """
import math
from pcvs.plugins import Plugin

class MyPlugin(Plugin):
    step = Plugin.Step.TEST_EVAL

    def run(self, *args, **kwargs):
    # this dict maps keys (it name) with values (it value)
    # returns True if the combination should be used
    return True
"""
        try:
            edited_code = click.edit(plugin_code,
                                     extension=".py",
                                     require_save=True)
            if edited_code is not None:
                self._details['runtime']['plugin'] = edited_code.encode('utf-8')
                self.flush_to_disk()
        except Exception as e:
            raise e

    def split_into_configs(self, prefix, blocklist, scope=None):
        """Convert the given profile into a list of basic blocks.

        This is the reverse operation of creating a profile (not the 'opposite').

        :param prefix: common prefix name used to name basic blocks.
        :type prefix: str
        :param blocklist: list of config.blocks to generate (all 5 by default
            but can be retrained)
        :type blocklist: list
        :param scope: config block scope, defaults to None
        :type scope: str, optional

        :raises AlreadyExistError: the created configuration
            block name already exist
        :return: list of created :class:`ConfigurationBlock`
        :rtype: list
        """
        objs = list()
        if 'all' in blocklist:
            blocklist = config.CONFIG_BLOCKS
        if scope is None:
            scope = self._scope

        for name in blocklist:
            c = config.ConfigurationBlock(name, prefix, scope)
            if c.is_found():
                raise ConfigException.AlreadyExistError(c.full_name)
            else:
                c.fill(self._details[name])
                objs.append(c)
        return objs

    @property
    def compiler(self):
        """Access the 'compiler' section.

        :return: the 'compiler' dict segment
        :rtype: dict
        """
        return self._details['compiler']

    @property
    def runtime(self):
        """Access the 'runtime' section.

        :return: the 'runtime' dict segment
        :rtype: dict
        """
        return self._details['runtime']

    @property
    def criterion(self):
        """Access the 'criterion' section.

        :return: the 'criterion' dict segment
        :rtype: dict
        """
        return self._details['criterion']

    @property
    def group(self):
        """Access the 'group' section.

        :return: the 'group' dict segment
        :rtype: dict
        """
        return self._details['group']

    @property
    def machine(self):
        """Access the 'machine' section.

        :return: the 'machine' dict segment
        :rtype: dict
        """
        return self._details['machine']
