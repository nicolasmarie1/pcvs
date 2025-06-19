import os
from typing import List

import jsonschema
from ruamel.yaml import YAML
from ruamel.yaml import YAMLError

import pcvs
from pcvs import io
from pcvs import NAME_BUILDIR
from pcvs import PATH_INSTDIR
from pcvs.helpers import git
from pcvs.helpers import pm
from pcvs.helpers.exceptions import CommonException
from pcvs.helpers.exceptions import ValidationException
from pcvs.io import Verbosity


# ###################################
# ###   YAML VALIDATION OBJECT   ####
# ###################q################
class ValidationScheme:
    """
    Object manipulating schemes (yaml) to enforce data formats.

    A validationScheme is instancied according to a 'model' (the format to
    validate). This instance can be used multiple times to check multiple
    streams belonging to the same model.
    """

    avail_list = []

    @classmethod
    def available_schemes(cls) -> List:
        """
        Return list of currently supported formats to be validated.

        The list is extracted from INSTALL/schemes/<model>-scheme.yml
        :return: List of available schemes.
        """
        if not cls.avail_list:
            cls.avail_list = []
            for f in os.listdir(os.path.join(PATH_INSTDIR, 'schemes/')):
                cls.avail_list.append(f.replace('-scheme.yml', ''))

        return cls.avail_list

    def __init__(self, name):
        """
        Create a new ValidationScheme instancen based on a given model.

        During initialisation the file scheme is loaded from disk.
        :param name: name
        :raises SchemeError: file is not found OR unable to load
        the YAML scheme file.
        """
        self.schema_name = name  # the name of the schema
        self.schema = None       # the content of the schema

        try:
            path = os.path.join(PATH_INSTDIR, f'schemes/{name}-scheme.yml')
            with open(path, 'r', encoding='utf-8') as fh:
                self.schema = YAML(typ='safe').load(fh)
        except (IOError, YAMLError) as er:
            raise ValidationException.SchemeError(
                f"Unable to load scheme {name}") from er

    def validate(self, content: dict, filepath: str):
        """
        Validate a given datastructure (dict) agasint the loaded scheme.

        :param content: json to validate
        :type content: dict
        :param filepath: the path of the file content come from
        :type filepath: str
        :raises FormatError: data are not valid
        :raises SchemeError: issue while applying scheme
        """
        if not filepath:
            io.console.warn("Validation operated on unknown file.")
        # assert filepath
        # template are use to validate default configuration
        # even if the file has not been created
        # assert os.path.isfile(filepath)
        try:
            jsonschema.validate(instance=content, schema=self.schema)
        except jsonschema.exceptions.ValidationError as e:
            raise ValidationException.FormatError(
                reason=f"Failed to validate input file: '{filepath}'\n"
                       f"Validation against schema '{self.schema_name}'\n"
                       f"Context is: \n {content}\n"
                       f"Schema is: \n {self.schema}\n"
                       f"Validation error message is:\n {e.message}\n"
            ) from e
        except jsonschema.exceptions.SchemaError as e:
            raise ValidationException.SchemeError(
                    name=self.schema_name, content=self.schema, error=e) from e


class Config(dict):
    """
    A 'Config' is a dict used to manage all configuration fields.

    While it can contain arbitrary data, the whole PCVS
    configuration is composed of 5 distinct 'categories', each being a single
    Config. These are then gathered in a `MetaConfig` object (see below)
    """

    def __init__(self, d: dict = {}):
        """
        Init the object.

        :param d: items of the configuration
        :type d: dict
        """
        super().__init__(**d)

    def validate(self, kw, filepath: str):
        """Check if the Config instance matches the expected format as declared
        in schemes/. As the 'category' is not carried by the object itself, it
        is provided by the function argument.

        :param kw: keyword describing the configuration to be validated (scheme)
        :type kw: str
        :param filepath: the path of the file kw come from
        :type filepath: str
        """
        assert filepath
        assert kw in ValidationScheme.available_schemes()
        ValidationScheme(kw).validate(self, filepath)

    def set_ifdef(self, k, v):
        """
        Shortcut function: init self[k] only if v is not None.

        :param k: name of value to add
        :type k: str
        :param v: value to add
        :type v: str
        """
        if v is not None:
            self[k] = v

    def set_nosquash(self, k, v):
        """
        Shortcut function: init self[k] only if v is not already set.

        :param k: name of value to add
        :type k: str
        :param v: value to add
        :type v: str
        """
        if k not in self:
            self[k] = v

    @classmethod
    def __to_dict(cls, d):
        for k, v in d.items():
            if isinstance(v, dict):  # is MetaConfig or v is Config:
                d[k] = Config.__to_dict(v)
        return dict(d)

    def to_dict(self):
        """Convert the Config() to regular dict."""
        return Config.__to_dict(self)

    def from_dict(self, d):
        """
        Fill the current Config from a given dict.

        :param d: dictionary to add
        :type d: dict
        """
        self.update(d)

    def from_file(self, filename):
        """
        Fill the current config from a given file

        :raises IOError: file does not exist OR badly formatted
        """
        try:
            with open(filename, 'r') as fh:
                d = YAML(typ='safe').load(fh)
                self.from_dict(d)
        except (IOError, YAMLError) as error:
            raise CommonException.IOError(
                "{} invalid or badly formatted".format(filename)) from error


class MetaConfig(Config):
    """
    Root configuration object.

    It is composed of Config(), categorizing each configuration blocks.
    This MetaConfig() contains the whole profile along with
    any validation and current run information.
    This configuration is used as a dict extension.

    The internal_config is used to initialize the internal config during unit test
    """
    validation_default_file = pcvs.PATH_VALCFG

    def __init__(self, d: dict = {}, internal_config: dict = {}):
        """
        Init the object.

        :param d: items of the configuration
        :type d: dict
        """
        super().__init__(d)
        self.__internal_config = internal_config

    def bootstrap_generic(self, subnode_name: str, node: dict, filepath: str):
        """
        Initialize a Config() object and store it under name 'node'.

        :param subnode_name: node name
        :type subnode_name: str
        :param node: node to initialize and add
        :type node: dict
        :param filepath: the path of the file subnode_name come from
        :type filepath: str
        :return: added subnode
        :rtype: dict
        """
        if subnode_name not in self:
            self[subnode_name] = Config(node)

        self[subnode_name].validate(subnode_name, filepath)
        return self[subnode_name]

    def bootstrap_from_profile(self, pf, filepath: str):
        """Bootstrap profile from dict"""

        self.bootstrap_compiler(pf['compiler'], filepath)
        self.bootstrap_runtime(pf['runtime'], filepath)
        self.bootstrap_machine(pf['machine'], filepath)
        self.bootstrap_criterion(pf['criterion'], filepath)
        self.bootstrap_group(pf['group'], filepath)

    def bootstrap_compiler(self, node, filepath: str):
        """
        Specific initialize for compiler config block.

        :param node: compiler block to initialize
        :type node: dict
        :param filepath: the path of the file node comme from
        :type filepath: str
        :return: added node
        :rtype: dict
        """
        subtree = self.bootstrap_generic('compiler', node, filepath)
        if 'package_manager' in subtree:
            self.set_internal('cc_pm', pm.identify(subtree['package_manager']))
        return subtree

    def bootstrap_runtime(self, node, filepath: str):
        """"Specific initialize for runtime config block
        :param node: runtime block to initialize
        :type node: dict
        :param filepath: the path of the file node comme from
        :type filepath: str
        :return: added node
        :rtype: dict"""
        subtree = self.bootstrap_generic('runtime', node, filepath)
        if 'package_manager' in subtree:
            self.set_internal('rt_pm', pm.identify(subtree['package_manager']))
        return subtree

    def bootstrap_group(self, node, filepath: str):
        """"Specific initialize for group config block.
        There is currently nothing to here but calling bootstrap_generic()
        :param node: runtime block to initialize
        :type node: dict
        :param filepath: the path of the file node comme from
        :type filepath: str
        :return: added node
        :rtype: dict
        """
        return self.bootstrap_generic('group', node, filepath)

    def bootstrap_validation_from_file(self, filepath: str):
        """
        Specific initialize for validation config block.

        This function loads a file containing the validation dict.
        :param filepath: path to file to be validated
        :type filepath: str
        :return:
        :rtype:
        :raises IOError: file is not found or badly formatted
        """
        node = {}
        if filepath is None:
            filepath = self.validation_default_file

        if os.path.isfile(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as fh:
                    node = YAML(typ='safe').load(fh)
            except (IOError, YAMLError) as e:
                raise CommonException.IOError(
                    f"Error(s) found while loading {filepath}") from e

        # some post-actions
        for field in ["output", "reused_build"]:
            if field in node:
                node[field] = os.path.abspath(node[field])

        if 'dirs' in node:
            node['dirs'] = {k: os.path.abspath(v) for k, v in node['dirs'].items()}

        return self.bootstrap_validation(node, filepath)

    def bootstrap_validation(self, node, filepath: str):
        """
        Specific initialize for validation config block.

        :param node: validation block to initialize
        :type node: dict
        :param filepath: path of the file node come from
        :type filepath: str
        :return: initialized node
        :rtype: dict
        """
        subtree = self.bootstrap_generic('validation', node, filepath)

        # Initialize default values when not set by user or default files
        subtree.set_nosquash('verbose', str(Verbosity.COMPACT))
        subtree.set_nosquash('print_level', 'none')
        subtree.set_nosquash('color', True)
        subtree.set_nosquash('default_profile', 'default')
        subtree.set_nosquash('output', os.path.join(os.getcwd(), NAME_BUILDIR))
        subtree.set_nosquash('background', False)
        subtree.set_nosquash('override', False)
        subtree.set_nosquash('dirs', None)
        subtree.set_nosquash("spack_recipe", None)
        subtree.set_nosquash('simulated', False)
        subtree.set_nosquash('anonymize', False)
        subtree.set_nosquash('onlygen', False)
        subtree.set_nosquash('timeout', None)
        subtree.set_nosquash('target_bank', None)
        subtree.set_nosquash('reused_build', None)
        subtree.set_nosquash('webreport', None)
        subtree.set_nosquash("only_success", False)
        subtree.set_nosquash("enable_report", False)
        subtree.set_nosquash('job_timeout', 3600)
        subtree.set_nosquash('per_result_file_sz', 10 * 1024 * 1024)
        subtree.set_nosquash('buildcache',
                             os.path.join(subtree['output'], 'cache'))
        subtree.set_nosquash('result', {"format": ['json']})
        subtree.set_nosquash(
            'author', {
                "name": git.get_current_username(),
                "email": git.get_current_usermail()
            })

        if 'format' not in subtree['result']:
            subtree['result']['format'] = ['json']
        if 'log' not in subtree['result']:
            subtree['result']['log'] = 1
        if 'logsz' not in subtree['result']:
            subtree['result']['logsz'] = 1024

        return subtree

    def bootstrap_machine(self, node, filepath: str):
        """
        Specific initialize for machine config block.

        :param node: machine block to initialize
        :type node: dict
        :param filepath: path of the file node come from
        :type filepath: str
        :return: initialized node
        :rtype: dict
        """
        subtree = self.bootstrap_generic('machine', node, filepath)
        subtree.set_nosquash('name', 'default')
        subtree.set_nosquash('nodes', 1)
        subtree.set_nosquash('cores_per_node', 1)
        subtree.set_nosquash('concurrent_run', 1)

        if 'default_partition' not in subtree or 'partitions' not in subtree:
            return

        # override default values by selected partition
        for elt in subtree.partitions:
            if elt.get('name',
                       subtree.default_partition) == subtree.default_partition:
                subtree.update(elt)
                break

        # redirect to direct programs if no wrapper is defined
        for kind in ['allocate', 'run', 'batch']:
            if not subtree.job_manager[kind].wrapper and subtree.job_manager[
                    kind].program:
                subtree.job_manager[kind].wrapper = subtree.job_manager[
                    kind].program
        return subtree

    def bootstrap_criterion(self, node, filepath: str):
        """"Specific initialize for criterion config block
        :param node: criterion block to initialize
        :type node: dict
        :return: initialized node
        :rtype: dict"""
        return self.bootstrap_generic('criterion', node, filepath)

    def set_internal(self, k, v):
        """manipulate the internal MetaConfig() node to store not-exportable data
        :param k: name of value to add
        :type k: str
        :param v: value to add
        :type v: str"""
        self.__internal_config[k] = v

    def get_internal(self, k):
        """manipulate the internal MetaConfig() node to load not-exportable data
        :param k: value to get
        :type k: str"""
        if k in self.__internal_config:
            return self.__internal_config[k]
        return None

    def dump_for_export(self) -> dict:
        """Export the whole configuration as a dict.
        Prune any __internal node beforehand.
        """
        return self.to_dict()


class GlobalConfig:
    """
    A static class to store a Global version of Metaconfig.

    To avoid carrying a global instancied object over the whole code, a
    class-scoped attribute allows to browse the global configuration from
    anywhere through `GlobalConfig.root`"
    """

    root = MetaConfig()
