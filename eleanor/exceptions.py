from enum import IntEnum

class RunCode(IntEnum):
    NOT_RUN = 0
    UNKNOWN = 1
    SUCCESS = 100
    EQPT_ERROR = 20
    EQ3_ERROR = 30
    NO_3P_FILE = 31
    FILE_ERROR_3P = 32
    FILE_ERROR_3O = 33
    EQ6_ERROR = 60
    NO_6O_FILE = 61
    FILE_ERROR_6O = 62
    OUTSIDE_SALINITY_WINDOW = 63,
    EQ6_EARLY_TERMINATION = 70

    def __str__(self):
        return {RunCode.NOT_RUN: 'not run',
                RunCode.UNKNOWN: 'an unrecognized error occured',
                RunCode.SUCCESS: 'success',
                RunCode.EQPT_ERROR: 'eqpt failed with an error',
                RunCode.EQ3_ERROR: 'eq3 failed with an error',
                RunCode.NO_3P_FILE: 'no 3p file generated',
                RunCode.FILE_ERROR_3P: 'eq3 ran but the 3p file contains errors',
                RunCode.FILE_ERROR_3O: 'eq6 ran but eleanor could not mine the 6o file',
                RunCode.EQ6_ERROR: 'eq6 failed with an error',
                RunCode.NO_6O_FILE: 'no 6o file generated',
                RunCode.FILE_ERROR_6O: 'eq6 ran but eleanor could not mine the 6o file',
                RunCode.OUTSIDE_SALINITY_WINDOW: 'total disolved solute is outside the desired salinity window',
                RunCode.EQ6_EARLY_TERMINATION: 'eq6 reaction path terminated early'
                }.get(self)


class EleanorException(Exception):
    def __init__(self, *args, code=None, **kwargs):
        super().__init__(*args, **kwargs)
        if code is None:
            self.code = RunCode.UNKNOWN
        else:
            self.code = code

    def __str__(self):
        return f"(code: {int(self.code)}) {super().__str__()}"

class Eq36Exception(EleanorException):
    pass

class EleanorFileException(EleanorException):
    def __init__(self, error, *args, **kwargs):
        super().__init__(self, str(error), *args, **kwargs)
