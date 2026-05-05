import unittest
from os.path import abspath, dirname, join, realpath
from typing import Any, cast

type AnyDict = dict[str, Any]  # pyright: ignore[reportExplicitAny]


def as_any_dict(value: object) -> AnyDict:
    return cast(AnyDict, value)


class TestCase(unittest.TestCase):
    @property
    def data_dir(self) -> str:
        return abspath(join(dirname(realpath(__file__)), "data"))

    @property
    def data0_dir(self) -> str:
        return self.data_path("db")

    def data0_path(self, *args: str) -> str:
        return self.data_path(self.data_dir, "db", *args)

    def data_path(self, *args: str) -> str:
        return join(self.data_dir, *args)
