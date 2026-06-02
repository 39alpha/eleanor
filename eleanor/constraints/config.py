from dataclasses import dataclass, field

from eleanor.util import guard_is_dict, guard_is_str


@dataclass(kw_only=True)
class ConstraintConfig:
    kind: str
    args: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        guard_is_str(self.kind, "kind")
        guard_is_dict(self.args, "args")
