from typing import TypedDict

import numpy as np

__all__ = [
    "Array1D",
    "Array2D",
    "EleanorKwargs",
]


class EleanorKwargs(TypedDict, total=False):
    """Options forwarded through the Eleanor / Runner / AbstractKernel chain.

    These are the keyword arguments that originate at the CLI (or at a
    programmatic caller) and flow as ``**kwargs`` through the forwarding
    methods all the way down to :class:`eleanor.runner.Runner` and the
    concrete :class:`eleanor.kernel.interface.AbstractKernel` leaves. Typing
    the bag as a single ``TypedDict`` lets ``pyright`` verify each hop
    without needing ``cast(Callable[..., T], …)`` at every forwarding site.
    """

    verbose: bool
    scratch: bool
    num_procs: int | None
    show_progress: bool


type Array1D[ScalarT: np.generic] = np.ndarray[tuple[int], np.dtype[ScalarT]]
type Array2D[ScalarT: np.generic] = np.ndarray[tuple[int, int], np.dtype[ScalarT]]
