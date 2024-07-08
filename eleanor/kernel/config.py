from dataclasses import dataclass

from eleanor.config.parameter import Parameter
from eleanor.typing import Self


@dataclass
class Config(object):
    type: str

    @property
    def is_fully_specified(self) -> bool:
        return True

    @property
    def parameters(self) -> list[Parameter]:
        return []

    def mean(self) -> Self:
        return self

    def to_row(self) -> dict:
        return {'type': self.type}
