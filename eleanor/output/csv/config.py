from dataclasses import dataclass
from typing import TypedDict

from ...exceptions import EleanorConfigurationException
from ...typing import cast


class CsvArgsRaw(TypedDict, total=False):
    filename: str
    query: dict[str, object]


@dataclass(frozen=True, init=False)
class CsvConfig(object):
    filename: str
    query: dict[str, object]

    def __init__(self, filename: object, query: object):
        if not isinstance(filename, str):
            raise EleanorConfigurationException('output.args.filename must be a string for output type "csv"')
        if not isinstance(query, dict):
            raise EleanorConfigurationException('output.args.query must be a mapping for output type "csv"')
        typed_query: dict[str, object] = {str(k): v for k, v in cast(dict[object, object], query).items()}
        object.__setattr__(self, "filename", filename)
        object.__setattr__(self, "query", typed_query)

    @staticmethod
    def from_raw(raw: CsvArgsRaw) -> "CsvConfig":
        return CsvConfig(
            filename=raw.get("filename"),
            query=raw.get("query"),
        )
