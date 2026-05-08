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


class EleanorShutdown(KeyboardInterrupt):
    """Signal-aware shutdown used by the run loop.

    Inherits from ``KeyboardInterrupt`` (a ``BaseException``) so it propagates
    through ``except Exception`` blocks while still unwinding all ``finally``
    chains.
    """

    signal_name: str | None

    def __init__(self, signal_name: str | None = None):
        message = f"shutdown requested by {signal_name}" if signal_name else "shutdown requested"
        super().__init__(message)
        self.signal_name = signal_name
