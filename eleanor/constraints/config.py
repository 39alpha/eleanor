from dataclasses import dataclass, field
from typing import TypedDict


class ConnfigRaw(TypedDict):
    type: str
    args: dict[str, object]


@dataclass
class Config(object):
    type: str
    args: dict[str, object] = field(default_factory=dict)
