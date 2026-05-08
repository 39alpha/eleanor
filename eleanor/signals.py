"""Signal handling helpers for Eleanor's dispatch loop.

This module translates ``SIGINT`` / ``SIGTERM`` into immediate
``KeyboardInterrupt`` propagation while still recording shutdown metadata on a
shared state object. No handlers are installed at module import time — the
library never mutates process-wide signal disposition as a side effect of
``import eleanor``.
"""

import signal
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from types import FrameType

    # signal.signal() accepts a callable, SIG_DFL, or SIG_IGN.
    # signal.getsignal() may additionally return None for handlers not
    # installed from Python.  _SignalHandler covers the full union so
    # _safe_prev can normalise the None case to SIG_DFL.
    type _SignalHandler = signal.Handlers | int | Callable[[int, FrameType | None], object] | None


def _safe_prev(handler: _SignalHandler) -> signal.Handlers | int | Callable[[int, FrameType | None], object]:
    """Normalise a ``getsignal`` return to something ``signal.signal`` accepts.

    ``signal.getsignal()`` returns ``None`` for handlers that were not
    installed from Python (e.g. a C extension's handler).  ``signal.signal()``
    does not accept ``None``, so fall back to ``SIG_DFL``.
    """
    if handler is None:
        return signal.SIG_DFL
    return handler


@dataclass
class ShutdownState:
    """Mutable flag shared between the signal handler and the dispatch loop."""

    requested: bool = False
    signal_name: str | None = None


@contextmanager
def shutdown_on_signal() -> "Generator[ShutdownState, None, None]":
    """Translate SIGINT/SIGTERM into an immediate ``KeyboardInterrupt``.

    On the first signal: set ``state.requested = True``, capture
    ``state.signal_name``, restore the previous handler so a *second* signal
    performs the pre-existing default behaviour (typically immediate
    termination), and raise ``KeyboardInterrupt`` to break out of any blocking
    operation in the main thread.

    Only installs handlers when called on the main thread of the main
    interpreter; otherwise yields a no-op state.  ``signal.signal()`` is
    main-thread-only and ``Eleanor.process()`` is always called from the
    main thread today, but the guard keeps the helper safe to reuse.
    """
    state = ShutdownState()

    if threading.current_thread() is not threading.main_thread():
        yield state
        return

    prev_int = _safe_prev(signal.getsignal(signal.SIGINT))
    prev_term = _safe_prev(signal.getsignal(signal.SIGTERM))

    def handler(signum: int, _frame: object) -> None:
        state.requested = True
        state.signal_name = signal.Signals(signum).name
        # Restore previous handlers immediately so a second signal escalates.
        _ = signal.signal(signal.SIGINT, prev_int)
        _ = signal.signal(signal.SIGTERM, prev_term)
        raise KeyboardInterrupt()

    _ = signal.signal(signal.SIGINT, handler)
    _ = signal.signal(signal.SIGTERM, handler)
    try:
        yield state
    finally:
        # Idempotent: if ``handler`` already restored, signal.signal accepts
        # the same value again.
        _ = signal.signal(signal.SIGINT, prev_int)
        _ = signal.signal(signal.SIGTERM, prev_term)
