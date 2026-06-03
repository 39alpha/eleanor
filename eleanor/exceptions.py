class EleanorException(Exception): ...


class EleanorShutdown(KeyboardInterrupt):
    signal_name: str | None

    def __init__(self, signal_name: str | None = None):
        message = f"shutdown requested by {signal_name}" if signal_name else "shutdown requested"
        super().__init__(message)
        self.signal_name = signal_name


__all__ = ["EleanorException", "EleanorShutdown"]
