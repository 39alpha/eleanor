from typing import override


class EleanorException(Exception):
    code: int | None

    def __init__(self, *args: object, code: int | None = None):
        super().__init__(*args)
        self.code = code

    @override
    def __str__(self) -> str:
        return f"(code: {self.code}) {super().__str__()}"


class EleanorFileException(EleanorException):
    def __init__(self, error: object, *args: object, code: int | None = None):
        super().__init__(self, str(error), *args, code=code)


class EleanorParserException(EleanorException):
    pass


class EleanorConfigurationException(EleanorException):
    pass
