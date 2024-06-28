from enum import IntEnum

from .kernel.eq36.codes import RunCode


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


class EleanorParserException(EleanorException):
    pass
