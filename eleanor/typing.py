from pathlib import Path
from typing import IO, TypedDict

import numpy as np


class EleanorKwargs(TypedDict, total=False):
    """Options forwarded through the Eleanor / Runner / AbstractKernel chain.

    These are the keyword arguments that originate at the CLI (or at a
    programmatic caller) and flow as ``**kwargs`` through the forwarding
    methods all the way down to :class:`eleanor.runner.Runner` and the
    concrete :class:`eleanor.kernel.interface.AbstractKernel` leaves.
    """

    verbose: bool
    scratch: bool
    num_procs: int | None
    show_progress: bool
    timing: bool


type Array1D[ScalarT: np.generic] = np.ndarray[tuple[int], np.dtype[ScalarT]]
type Array2D[ScalarT: np.generic] = np.ndarray[tuple[int, int], np.dtype[ScalarT]]
type StrPath = str | Path

type ReadStream = IO[str] | IO[bytes]

__all__ = [
    "Array1D",
    "Array2D",
    "EleanorKwargs",
    "ReadStream",
    "StrPath",
]
