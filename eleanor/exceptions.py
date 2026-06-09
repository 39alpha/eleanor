class EleanorException(Exception): ...


class EleanorShutdown(KeyboardInterrupt):
    signal_name: str | None

    def __init__(self, signal_name: str | None = None) -> None:
        message = f"shutdown requested by {signal_name}" if signal_name else "shutdown requested"
        super().__init__(message)
        self.signal_name = signal_name


class EleanorWarning(UserWarning): ...


__all__ = ["EleanorException", "EleanorShutdown", "EleanorWarning"]
