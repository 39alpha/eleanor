from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import CsvConfig as CsvConfig
    from .sink import CsvSink as CsvSink


def __getattr__(name: str) -> object:
    if name == "CsvConfig":
        from .config import CsvConfig

        return CsvConfig
    if name == "CsvSink":
        from .sink import CsvSink

        return CsvSink
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CsvConfig",
    "CsvSink",
]
