from dataclasses import dataclass, field
from typing import Self, TypedDict, cast

from eleanor.exceptions import EleanorConfigurationException


class ConfigRaw(TypedDict, total=False):
    """Schema for the ``executor`` section of a raw config document."""

    kind: str
    args: dict[str, object]
    chunks_per_worker: int


@dataclass
class Config(object):
    kind: str = "multiprocessing"
    args: dict[str, object] = field(default_factory=dict)
    chunks_per_worker: int = 10

    def __post_init__(self):
        if self.chunks_per_worker <= 0:
            msg = f'the chunks_per_worker value "{self.chunks_per_worker}" is invalid; choose a value >= 1'
            raise EleanorConfigurationException(msg)

    @classmethod
    def from_raw(cls, raw: ConfigRaw) -> Self:
        if cast(dict[str, object], cast(object, raw)).get("backend") is not None:
            raise EleanorConfigurationException("the executor.type config option has been renamed executor.kind")

        return cls(
            kind=raw.get("kind", "multiprocessing"),
            args=raw.get("args", {}),
            chunks_per_worker=raw.get("chunks_per_worker", 10),
        )


__all__ = [
    "ConfigRaw",
    "Config",
]
