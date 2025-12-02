import os
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

        The list is extracted from INSTALL/schemes/<model>-scheme.yml
        :return: List of available schemes.
        """
        if not cls.avail_list:
            cls.avail_list = []
            for f in os.listdir(os.path.join(PATH_INSTDIR, "schemes/")):
                cls.avail_list.append(f.replace("-scheme.yml", ""))

        return cls.avail_list

    def __init__(self, schema_name: str):
        """
        Create a new ValidationScheme instance based on a given model.

        During initialisation the file scheme is loaded from disk.
        :param name: name
        :raises SchemeError: file is not found OR unable to load
        the YAML scheme file.
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
        :type content: dict
        :param filepath: the path of the file content come from
        :type filepath: str
        :raises FormatError: data are not valid
        :raises SchemeError: issue while applying scheme
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
            raise ValidationException.FormatError(
                reason=f"\nFailed to validate input file: '{filepath}'\n"
                f"Validation against schema '{self.schema_name}'\n"
                f"Context is: \n {content}\n"
                f"Schema is: \n {self.schema}\n"
                f"Validation error message is:\n {e.message}\n"
            ) from e
        except jsonschema.exceptions.SchemaError as e:
            raise ValidationException.SchemeError(
                name=self.schema_name, content=self.schema, error=e
            ) from e
