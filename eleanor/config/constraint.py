from dataclasses import dataclass, field
from typing import Self

from eleanor.exceptions import EleanorError
from eleanor.util import guard_is_dict, guard_is_str, require_dict, require_str


@dataclass(kw_only=True)
class ConstraintConfig:
    kind: str
    args: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        guard_is_str(self.kind, "kind")
        guard_is_dict(self.args, "args")

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        kind = require_str(raw.get("kind"), "constraint.kind")
        if "args" in raw:
            if set(raw) - {"kind", "args"}:
                msg = "constraint configuration cannot mix flat and nested args"
                raise EleanorError(msg)
            args: dict[str, object] = require_dict(raw["args"], "args")
        else:
            args = {k: v for k, v in raw.items() if k != "kind"}
        return cls(kind=kind, args=args)
