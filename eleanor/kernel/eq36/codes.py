from enum import IntEnum
from typing import override


class RunCode(IntEnum):
    NOT_RUN = 0
    UNKNOWN = 1
    SUCCESS = 100
    EQPT_ERROR = 20
    EQ3_ERROR = 30
    NO_3P_FILE = 31
    FILE_ERROR_3P = 32
    FILE_ERROR_3O = 33
    NO_3O_FILE = 34
    EQ3_EARLY_TERMINATION = 35
    EQ6_ERROR = 60
    NO_6O_FILE = 61
    FILE_ERROR_6O = 62
    OUTSIDE_SALINITY_WINDOW = 63
    EQ6_EARLY_TERMINATION = 70
    EQ36_TIMEOUT = 90
    PARSER_ERROR = 91

    @override
    def __str__(self) -> str:
        message = {
            RunCode.NOT_RUN: "not run",
            RunCode.UNKNOWN: "an unrecognized error occurred",
            RunCode.SUCCESS: "success",
            RunCode.EQPT_ERROR: "eqpt failed with an error",
            RunCode.EQ3_ERROR: "eq3 failed with an error",
            RunCode.NO_3P_FILE: "no 3p file generated",
            RunCode.FILE_ERROR_3P: "eq3 ran but the 3p file contains errors",
            RunCode.FILE_ERROR_3O: "eq6 ran but eleanor could not mine the 6o file",
            RunCode.NO_3O_FILE: "no 3o file generated",
            RunCode.EQ6_EARLY_TERMINATION: "eq3 exited early for some reason",
            RunCode.EQ6_ERROR: "eq6 failed with an error",
            RunCode.NO_6O_FILE: "no 6o file generated",
            RunCode.FILE_ERROR_6O: "eq6 ran but eleanor could not mine the 6o file",
            RunCode.OUTSIDE_SALINITY_WINDOW: "total dissolved solute is outside the desired salinity window",
            RunCode.EQ6_EARLY_TERMINATION: "eq6 reaction path terminated early",
            RunCode.EQ36_TIMEOUT: "eq36 timed out",
            RunCode.PARSER_ERROR: "failed to parse an eq36 output file",
        }.get(self)
        if message is None:
            raise TypeError(f"missing string mapping for {self.__class__.__name__}.{self.name}")
        return message
