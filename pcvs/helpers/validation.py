import os
import pprint
from typing import Any

import jsonschema
from ruamel.yaml import YAML
from ruamel.yaml import YAMLError

from pcvs import io
from pcvs import PATH_INSTDIR
from pcvs.helpers.exceptions import ValidationException


class ValidationScheme:
    """
    Object manipulating schemes (yaml) to enforce data formats.

    A validationScheme is instancied according to a 'model' (the format to
    validate). This instance can be used multiple times to check multiple
    streams belonging to the same model.
    """

    avail_list: list[str] = []

    @classmethod
    def available_schemes(cls) -> list:
        """
        Return list of currently supported formats to be validated.

        The list is extracted from INSTALL/schemes/generated/<model>-scheme.yml
        :return: List of available schemes.
        """
        if not cls.avail_list:
            cls.avail_list = []
            for f in os.listdir(os.path.join(PATH_INSTDIR, "schemes/generated/")):
                cls.avail_list.append(f.replace("-scheme.yml", ""))

        return cls.avail_list

    def __init__(self, schema_name: str):
        """
        Create a new ValidationScheme instance based on a given model.

        During initialisation the file scheme is loaded from disk.

        :param schema_name: Name of the schema that will be loaded for validation.
        :raises ValidationException.InvalidSchemeError: file is not found OR unable to load the YAML scheme file.

        # noqa: DAR401
        # noqa: DAR402
        """
        self.schema_name = schema_name
        self.schema: Any = None  # the content of the schema

        try:
            path = os.path.join(PATH_INSTDIR, f"schemes/generated/{self.schema_name}-scheme.yml")
            with open(path, "r", encoding="utf-8") as fh:
                self.schema = YAML(typ="safe").load(fh)
        except (IOError, YAMLError) as er:
            raise ValidationException.InvalidSchemeError(schema=self.schema_name) from er

    def validate(self, content: dict, filepath: str) -> None:
        """
        Validate a given datastructure (dict) agasint the loaded scheme.

        :param content: json to validate
        :param filepath: the path of the file content come from
        :raises ValidationException.FormatError: data are not valid
        :raises ValidationException.SchemeError: issue while applying scheme

        # noqa: DAR401
        # noqa: DAR402
        """
        assert filepath
        if not filepath:
            io.console.warn("Validation operated on unknown file.")
        # assert filepath
        # template are use to validate default configuration
        # even if the file has not been created
        # assert os.path.isfile(filepath)
        try:
            jsonschema.validate(instance=content, schema=self.schema)
        except jsonschema.exceptions.ValidationError as e:
            fe = ValidationException.FormatError(reason="Failed to validate input file.")
            fe.add_dbg("file path", filepath)
            fe.add_dbg("validation schema", self.schema_name)
            fe.add_dbg("YAML validator error", e.message)
            fe.add_dbg("file content", pprint.pformat(content))
            fe.add_dbg("raw schema", pprint.pformat(self.schema))
            raise fe from e
        except jsonschema.exceptions.SchemaError as e:
            raise ValidationException.SchemeError(
                name=self.schema_name, content=self.schema, error=e
            ) from e
