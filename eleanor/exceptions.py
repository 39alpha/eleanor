from enum import IntEnum


class EleanorException(Exception):

    def __init__(self, *args, code=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.code = code

    def __str__(self):
        return f"(code: {self.code}) {super().__str__()}"


class EleanorFileException(EleanorException):

    def __init__(self, error, *args, **kwargs):
        super().__init__(self, str(error), *args, **kwargs)


class EleanorParserException(EleanorException):
    pass


class EleanorConfigurationException(EleanorException):
    pass
