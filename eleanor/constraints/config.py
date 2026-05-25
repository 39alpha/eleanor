from dataclasses import dataclass, field
from typing import TypedDict

from eleanor.typing import RawMap


class ConnfigRaw(TypedDict):
    type: str
    args: RawMap


@dataclass
class Config(object):
    type: str
    args: RawMap = field(default_factory=dict)
