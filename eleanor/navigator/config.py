from dataclasses import dataclass
from typing import TypedDict

from eleanor.typing import RawMap


class ConfigRaw(TypedDict, total=False):
    kind: str
    args: RawMap


@dataclass(init=False)
class Config(object):
    kind: str
    args: RawMap

    def __init__(self, kind: str = "random", args: RawMap | None = None):
        self.kind = kind
        self.args = args if args is not None else {}
