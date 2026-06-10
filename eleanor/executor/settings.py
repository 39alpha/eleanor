from dataclasses import dataclass
from typing import Self

from eleanor.exceptions import EleanorError
from eleanor.settings import Settings
from eleanor.util import guard_is_int, guard_is_int_or_none, require_opt_int


@dataclass(kw_only=True)
class ExecutorSettings(Settings):
    num_workers: int | None = None
    chunks_per_worker: int = 10

    def __post_init__(self) -> None:
        guard_is_int_or_none(self.num_workers, "num_workers")
        if self.num_workers is not None and self.num_workers <= 0:
            msg = f"num_workers must be greater than zero; got {self.num_workers}"
            raise EleanorError(msg)

        guard_is_int(self.chunks_per_worker, "chunks_per_worker")
        if self.chunks_per_worker <= 0:
            msg = f"chunks_per_worker must be greater than zero; got {self.chunks_per_worker}"
            raise EleanorError(msg)

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        num_workers = require_opt_int(raw.get("num_workers"), "num_workers")
        chunks_per_worker = require_opt_int(raw.get("chunks_per_worker"), "chunks_per_worker")

        if chunks_per_worker is not None:
            return cls(chunks_per_worker=chunks_per_worker, num_workers=num_workers)

        return cls(num_workers=num_workers)


__all__ = ["ExecutorSettings"]
