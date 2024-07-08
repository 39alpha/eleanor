from dataclasses import dataclass

from ..exceptions import EleanorParserException
from ..hanger.tool_room import is_list_of
from ..typing import Optional


@dataclass(init=False)
class Suppression(object):
    name: Optional[str]
    type: Optional[str]
    exceptions: list[str]

    def __init__(self, name: Optional[str], type: Optional[str], exceptions: list[str]):
        if name is None and type is None:
            raise EleanorParserException(f'suppression must have a name or a type')

        self.name = name
        self.type = type
        self.exceptions = exceptions

    @staticmethod
    def from_dict(raw: dict, name: Optional[str] = None):
        if name is None:
            name = raw.get('name')

        if not isinstance(name, (str, type(None))):
            raise EleanorParserException(f'suppression name must be a string')

        suppression_type = raw.get('type')
        if not isinstance(suppression_type, (str, type(None))):
            raise EleanorParserException(f'supression type must be a string')

        exceptions = raw.get('except', [])
        if not is_list_of(exceptions, (str), allowNone=False):
            raise EleanorParserException(f'suppression exceptions must be a list of int or float')

        return Suppression(name, suppression_type, exceptions)
