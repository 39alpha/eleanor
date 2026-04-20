from typing import Protocol, runtime_checkable


@runtime_checkable
class ProgressHandle(Protocol):

    def put(self, msg: bool | int) -> None:
        ...
