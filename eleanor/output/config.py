from dataclasses import dataclass, field
from typing import Self, TypedDict, cast

from eleanor.exceptions import EleanorConfigurationException


class ConfigRaw(TypedDict, total=False):
    """Schema for the ``output`` section of a raw config document."""

    kind: str
    args: dict[str, object]


@dataclass
class Config(object):
    kind: str | None = None
    args: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: ConfigRaw) -> Self:
        if cast(dict[str, object], cast(object, raw)).get("type") is not None:
            raise EleanorConfigurationException("the output.type config option has been renamed output.kind")

        output_args_raw: object = raw.get("args", {})
        if not isinstance(output_args_raw, dict):
            raise EleanorConfigurationException("output.args must be a dict")
        output_args_items = cast(dict[object, object], output_args_raw).items()
        output_args: dict[str, object] = {str(k): v for k, v in output_args_items}
        return cls(kind=raw.get("kind"), args=output_args)


__all__ = [
    "ConfigRaw",
    "Config",
]
